"""Tests für lsa_pruefung (ausführen mit: python -m pytest)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from lsa_pruefung import zyklus
from lsa_pruefung.cli import main
from lsa_pruefung.modell import InputError, load_junction
from lsa_pruefung.pruefungen import check_program
from lsa_pruefung.zwischenzeiten import intergreen_matrix

BEISPIEL = Path(__file__).parents[1] / "beispiele" / "knoten_hauptstrasse_ringstrasse"


@pytest.fixture
def projekt(tmp_path: Path) -> Path:
    """Kopie des Beispielprojekts, die ein Test verändern darf."""
    ziel = tmp_path / "knoten"
    shutil.copytree(BEISPIEL, ziel, ignore=shutil.ignore_patterns("ausgabe"))
    return ziel


def _set_program(folder: Path, rows: list[str], cycle: int = 70) -> None:
    (folder / "signalprogramm_P1.csv").write_text(
        "signalgruppe;gruen_beginn_s;gruen_ende_s\n" + "\n".join(rows) + "\n", encoding="utf-8")
    meta = json.loads((folder / "knoten.json").read_text(encoding="utf-8"))
    meta["programme"] = [{"id": "P1", "umlaufzeit_s": cycle, "datei": "signalprogramm_P1.csv"}]
    (folder / "knoten.json").write_text(json.dumps(meta), encoding="utf-8")


P1_OK = ["K1;65;31", "K2;65;31", "F3;65;25", "F4;65;25",
         "K3;37;59", "K4;37;59", "F1;38;53", "F2;38;53"]


# --------------------------------------------------------------------------- #
# Zyklische Zeitachse
# --------------------------------------------------------------------------- #

def test_dauer_ueber_umlaufende():
    assert zyklus.duration(65, 31, 70) == 36
    assert zyklus.seconds(68, 2, 70) == {68, 69, 0, 1}


def test_abstand_vorwaerts_im_umlauf():
    assert zyklus.gap(64, 0, 70) == 6
    assert zyklus.gap(30, 34, 70) == 4


# --------------------------------------------------------------------------- #
# Zwischenzeiten
# --------------------------------------------------------------------------- #

def test_zwischenzeit_handrechnung_kfz():
    # K1 -> K3: t_z = 3 + (14 + 6) / 10 - 9 / 11.1 = 4.19 s -> aufgerundet 5 s
    calc = intergreen_matrix(load_junction(BEISPIEL))[("K1", "K3")]
    assert calc.exact_s == pytest.approx(3 + 20 / 10 - 9 / 11.1)
    assert calc.required_s == 5


def test_zwischenzeit_handrechnung_fussgaenger():
    # F1 -> K1: t_z = 0 + 14 / 1.2 - 2 / 11.1 = 11.49 s -> 12 s
    calc = intergreen_matrix(load_junction(BEISPIEL))[("F1", "K1")]
    assert calc.required_s == 12


def test_ganzzahliges_ergebnis_wird_nicht_aufgerundet():
    # K1 -> F1: t_z = 3 + (4 + 6) / 10 - 0 / 1.5 = 4.0 s -> bleibt 4 s
    assert intergreen_matrix(load_junction(BEISPIEL))[("K1", "F1")].required_s == 4


def test_abbieger_mit_2_s_ueberfahrzeit(projekt: Path):
    # Abbieger (R >= 10 m): t_ü = 2 s, v_r = 7 m/s -> 2 + (14 + 6) / 7 - 9 / 11.1 = 4.05 s -> 5 s
    # enger Abbieger (R < 10 m): v_r = 5 m/s -> 2 + 20 / 5 - 9 / 11.1 = 5.19 s -> 6 s
    path = projekt / "konfliktgeometrie.csv"
    text = path.read_text(encoding="utf-8")
    text = text.replace("K1;K3;14;9;geradeaus;", "K1;K3;14;9;abbiegend;")
    text = text.replace("K2;K4;14;9;geradeaus;", "K2;K4;14;9;abbiegend_eng;")
    path.write_text(text, encoding="utf-8")
    matrix = intergreen_matrix(load_junction(projekt))
    assert matrix[("K1", "K3")].t_ue == 2.0
    assert matrix[("K1", "K3")].exact_s == pytest.approx(2 + 20 / 7 - 9 / 11.1)
    assert matrix[("K1", "K3")].required_s == 5
    assert matrix[("K2", "K4")].required_s == 6


def test_vorgabewert_ueberschreibt_berechnung(projekt: Path):
    path = projekt / "konfliktgeometrie.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("K1;K3;14;9;geradeaus;",
                                                              "K1;K3;14;9;geradeaus;9"),
                    encoding="utf-8")
    calc = intergreen_matrix(load_junction(projekt))[("K1", "K3")]
    assert calc.required_s == 9 and calc.source == "Vorgabe"


# --------------------------------------------------------------------------- #
# Prüfregeln
# --------------------------------------------------------------------------- #

def test_korrektes_programm_besteht():
    res = check_program(load_junction(BEISPIEL), "P1")
    assert res.passed and not res.warnings
    assert all(c.ok for c in res.intergreen_checks)
    assert len(res.intergreen_checks) == 24


def test_fehlerhafter_entwurf_wird_erkannt():
    res = check_program(load_junction(BEISPIEL), "P2")
    found = {(f.rule, f.groups) for f in res.findings}
    assert found == {
        ("KF-01", ("K1", "K4")),
        ("KF-01", ("K2", "K4")),
        ("MF-01", ("F1",)),
        ("ZZ-01", ("K1", "K3")),
        ("ZZ-01", ("K2", "K3")),
        ("ZZ-01", ("F3", "K4")),
        ("ZZ-01", ("F4", "K4")),
        ("STR-03", ("F2",)),
    }


def test_zwischenzeit_ueber_umlaufende(projekt: Path):
    # K4 endet bei 66, K1 und F3 beginnen bei 0 (= 70): je nur 4 s statt 6 s
    rows = ["K1;0;36", "K2;0;36", "F3;0;30", "F4;0;30",
            "K3;42;64", "K4;42;66", "F1;43;58", "F2;43;58"]
    _set_program(projekt, rows)
    res = check_program(load_junction(projekt), "P1")
    assert {(f.rule, f.groups) for f in res.findings} == {("ZZ-01", ("K4", "K1")),
                                                         ("ZZ-01", ("K4", "F3"))}
    assert all("vorhanden 4 s" in f.message for f in res.findings)


def test_konflikt_ueber_umlaufende(projekt: Path):
    rows = [r for r in P1_OK if not r.startswith("K3")] + ["K3;60;2"]  # 60…70 und 0…2
    _set_program(projekt, rows)
    res = check_program(load_junction(projekt), "P1")
    assert ("KF-01", ("K1", "K3")) in {(f.rule, f.groups) for f in res.findings}
    assert res.conflict_seconds[("K1", "K3")] == {65, 66, 67, 68, 69, 0, 1}


def test_einseitiger_konflikt_ergibt_warnung(projekt: Path):
    path = projekt / "konfliktgeometrie.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("K3;K1;8;12;geradeaus;\n", ""),
                    encoding="utf-8")
    res = check_program(load_junction(projekt), "P1")
    assert ("STR-04", ("K1", "K3")) in {(f.rule, f.groups) for f in res.findings}


def test_falsche_gelbzeit(projekt: Path):
    path = projekt / "signalgruppen.csv"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "K1;Kfz;Zufahrt Nord (Hauptstraße);50;3;1;", "K1;Kfz;Zufahrt Nord (Hauptstraße);60;3;1;"),
        encoding="utf-8")
    res = check_program(load_junction(projekt), "P1")
    assert ("GZ-01", ("K1",)) in {(f.rule, f.groups) for f in res.findings}


def test_unbekannte_gruppe_und_zeit_ausserhalb(projekt: Path):
    _set_program(projekt, P1_OK + ["K9;0;10", "F1;60;75"])
    rules = {f.rule for f in check_program(load_junction(projekt), "P1").findings}
    assert {"STR-01", "STR-02"} <= rules


# --------------------------------------------------------------------------- #
# Eingabefehler und Kommandozeile
# --------------------------------------------------------------------------- #

def test_dezimalzahl_bei_sekunden_wird_abgelehnt(projekt: Path):
    _set_program(projekt, P1_OK[:-1] + ["F2;37;53,5"])
    with pytest.raises(InputError, match="ganze Sekunden"):
        load_junction(projekt)


def test_fehlende_spalte(projekt: Path):
    (projekt / "signalgruppen.csv").write_text("id;typ\nK1;Kfz\n", encoding="utf-8")
    with pytest.raises(InputError, match="Spalte"):
        load_junction(projekt)


def test_cli_rueckgabewerte_und_berichte(tmp_path: Path):
    out = tmp_path / "out"
    assert main(["pruefe", str(BEISPIEL), "-p", "P1", "-o", str(out)]) == 0
    assert main(["pruefe", str(BEISPIEL), "-p", "P2", "-o", str(out)]) == 1
    assert main(["pruefe", str(tmp_path / "gibt_es_nicht"), "-o", str(out)]) == 2
    for name in ("pruefbericht_P1.html", "pruefbericht_P1.md", "pruefergebnis_P1.json",
                 "signalzeitenplan_P1.png"):
        assert (out / name).stat().st_size > 0
    data = json.loads((out / "pruefergebnis_P2.json").read_text(encoding="utf-8"))
    assert data["zusammenfassung"]["fehler"] == 7
