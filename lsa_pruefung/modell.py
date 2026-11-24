"""Datenmodell und Einlesen eines LSA-Projekts (Knotenpunkt).

Ein Projektordner enthält:

* ``knoten.json``            – Stammdaten und Liste der Signalprogramme
* ``signalgruppen.csv``      – Signalgruppen mit Verkehrsart, Gelb-/Rot-Gelb-Zeit
* ``konfliktgeometrie.csv``  – feindliche Signalgruppen mit Räum-/Einfahrwegen
* ``signalprogramm_*.csv``   – Freigabezeiten je Signalprogramm
* ``parameter.json``         – optional, überschreibt die Standardparameter

CSV-Dateien verwenden das Semikolon als Trennzeichen (Excel-Standard in DE).
"""

from __future__ import annotations

import copy
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PARAMETER_FILE = Path(__file__).with_name("rilsa_parameter.json")
MOVEMENTS = ("geradeaus", "abbiegend", "abbiegend_eng")


class InputError(ValueError):
    """Fehler in den Eingabedaten (Datei, Zeile und Ursache in der Meldung)."""


@dataclass(frozen=True)
class SignalGroup:
    id: str
    typ: str                    # Kfz | Rad | Fg (weitere über parameter.json)
    name: str
    speed_kmh: float | None     # zulässige Geschwindigkeit, nur für Kfz relevant
    amber_s: int                # Gelbzeit
    red_amber_s: int            # Rot-Gelb-Zeit
    min_green_s: int | None     # None -> Standardwert der Verkehrsart


@dataclass(frozen=True)
class ConflictGeometry:
    clearing: str               # räumende Signalgruppe
    entering: str               # einfahrende Signalgruppe
    clearing_distance_m: float  # Räumweg s_r
    entering_distance_m: float  # Einfahrweg s_e
    clearing_movement: str      # geradeaus | abbiegend (R >= 10 m) | abbiegend_eng (R < 10 m)
    intergreen_override_s: int | None = None  # feste Vorgabe statt Berechnung


@dataclass(frozen=True)
class GreenInterval:
    group: str
    start: int                  # Freigabebeginn [s im Umlauf]
    end: int                    # Freigabeende   [s im Umlauf]
    line: int = 0               # Zeile in der CSV-Datei (für Meldungen)


@dataclass
class SignalProgram:
    id: str
    cycle_s: int
    description: str
    greens: list[GreenInterval] = field(default_factory=list)


@dataclass
class Junction:
    name: str
    location: str
    groups: dict[str, SignalGroup]
    conflicts: list[ConflictGeometry]
    programs: dict[str, SignalProgram]
    parameters: dict
    folder: Path


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #

def _read_csv(path: Path, required: list[str]) -> list[tuple[int, dict[str, str]]]:
    if not path.exists():
        raise InputError(f"Datei fehlt: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in required if c not in header]
        if missing:
            raise InputError(f"{path.name}: Spalte(n) fehlen: {', '.join(missing)}")
        rows = []
        for line_no, raw in enumerate(reader, start=2):
            row = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
            if not any(row.values()) or row.get(required[0], "").startswith("#"):
                continue  # Leer- und Kommentarzeilen überspringen
            rows.append((line_no, row))
        return rows


def _number(value: str, path: Path, line: int, column: str, *, integer: bool = False,
            optional: bool = False):
    value = value.replace(",", ".")  # deutsches Dezimalkomma zulassen
    if value == "":
        if optional:
            return None
        raise InputError(f"{path.name}, Zeile {line}: Wert in Spalte '{column}' fehlt")
    try:
        number = float(value)
    except ValueError:
        raise InputError(
            f"{path.name}, Zeile {line}: '{value}' in Spalte '{column}' ist keine Zahl"
        ) from None
    if integer:
        if not number.is_integer():
            raise InputError(
                f"{path.name}, Zeile {line}: Spalte '{column}' erwartet ganze Sekunden, "
                f"gefunden {value}"
            )
        return int(number)
    return number


def _merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_parameters(folder: Path | None = None) -> dict:
    params = json.loads(DEFAULT_PARAMETER_FILE.read_text(encoding="utf-8"))
    if folder is not None:
        own = folder / "parameter.json"
        if own.exists():
            params = _merge(params, json.loads(own.read_text(encoding="utf-8")))
    return params


# --------------------------------------------------------------------------- #
# Einlesen
# --------------------------------------------------------------------------- #

def load_groups(path: Path, params: dict) -> dict[str, SignalGroup]:
    rows = _read_csv(path, ["id", "typ", "bezeichnung", "v_zul_kmh", "gelb_s", "rotgelb_s",
                            "mindestfreigabe_s"])
    known_types = set(params["verkehrsarten"])
    groups: dict[str, SignalGroup] = {}
    for line, row in rows:
        gid = row["id"]
        if gid in groups:
            raise InputError(f"{path.name}, Zeile {line}: Signalgruppe '{gid}' doppelt")
        if row["typ"] not in known_types:
            raise InputError(
                f"{path.name}, Zeile {line}: unbekannte Verkehrsart '{row['typ']}' "
                f"(erlaubt: {', '.join(sorted(known_types))})"
            )
        groups[gid] = SignalGroup(
            id=gid,
            typ=row["typ"],
            name=row["bezeichnung"],
            speed_kmh=_number(row["v_zul_kmh"], path, line, "v_zul_kmh", optional=True),
            amber_s=_number(row["gelb_s"] or "0", path, line, "gelb_s", integer=True),
            red_amber_s=_number(row["rotgelb_s"] or "0", path, line, "rotgelb_s", integer=True),
            min_green_s=_number(row["mindestfreigabe_s"], path, line, "mindestfreigabe_s",
                                integer=True, optional=True),
        )
    if not groups:
        raise InputError(f"{path.name}: keine Signalgruppen definiert")
    return groups


def load_conflicts(path: Path) -> list[ConflictGeometry]:
    rows = _read_csv(path, ["raeumend", "einfahrend", "raeumweg_m", "einfahrweg_m",
                            "bewegung", "zwischenzeit_vorgabe_s"])
    conflicts: list[ConflictGeometry] = []
    seen: set[tuple[str, str]] = set()
    for line, row in rows:
        key = (row["raeumend"], row["einfahrend"])
        if key[0] == key[1]:
            raise InputError(f"{path.name}, Zeile {line}: Signalgruppe ist zu sich selbst feindlich")
        if key in seen:
            raise InputError(f"{path.name}, Zeile {line}: Konfliktpaar {key[0]} -> {key[1]} doppelt")
        seen.add(key)
        movement = (row["bewegung"] or "geradeaus").lower()
        if movement not in MOVEMENTS:
            raise InputError(
                f"{path.name}, Zeile {line}: Bewegung '{row['bewegung']}' unbekannt "
                f"(erlaubt: {', '.join(MOVEMENTS)})"
            )
        conflicts.append(ConflictGeometry(
            clearing=key[0],
            entering=key[1],
            clearing_distance_m=_number(row["raeumweg_m"], path, line, "raeumweg_m"),
            entering_distance_m=_number(row["einfahrweg_m"], path, line, "einfahrweg_m"),
            clearing_movement=movement,
            intergreen_override_s=_number(row["zwischenzeit_vorgabe_s"], path, line,
                                          "zwischenzeit_vorgabe_s", integer=True, optional=True),
        ))
    return conflicts


def load_program(path: Path, program_id: str, cycle_s: int, description: str) -> SignalProgram:
    rows = _read_csv(path, ["signalgruppe", "gruen_beginn_s", "gruen_ende_s"])
    program = SignalProgram(id=program_id, cycle_s=cycle_s, description=description)
    for line, row in rows:
        program.greens.append(GreenInterval(
            group=row["signalgruppe"],
            start=_number(row["gruen_beginn_s"], path, line, "gruen_beginn_s", integer=True),
            end=_number(row["gruen_ende_s"], path, line, "gruen_ende_s", integer=True),
            line=line,
        ))
    return program


def load_junction(folder: str | Path) -> Junction:
    folder = Path(folder)
    meta_path = folder / "knoten.json"
    if not meta_path.exists():
        raise InputError(f"Datei fehlt: {meta_path}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"knoten.json ist kein gültiges JSON: {exc}") from None

    params = load_parameters(folder)
    groups = load_groups(folder / "signalgruppen.csv", params)
    conflicts = load_conflicts(folder / "konfliktgeometrie.csv")

    programs: dict[str, SignalProgram] = {}
    for entry in meta.get("programme", []):
        try:
            pid, cycle, file_name = entry["id"], entry["umlaufzeit_s"], entry["datei"]
        except KeyError as exc:
            raise InputError(f"knoten.json: Programmeintrag ohne Feld {exc}") from None
        if not isinstance(cycle, int) or cycle <= 0:
            raise InputError(f"knoten.json: Umlaufzeit von {pid} muss eine positive ganze Zahl sein")
        programs[pid] = load_program(folder / file_name, pid, cycle, entry.get("beschreibung", ""))
    if not programs:
        raise InputError("knoten.json: keine Signalprogramme eingetragen")

    return Junction(
        name=meta.get("name", folder.name),
        location=meta.get("ort", ""),
        groups=groups,
        conflicts=conflicts,
        programs=programs,
        parameters=params,
        folder=folder,
    )
