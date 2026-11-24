"""Prüfregeln für Signalprogramme.

Regel-Kennungen
---------------
STR-01  Signalprogramm enthält unbekannte Signalgruppe              FEHLER
STR-02  Zeitpunkt außerhalb des Umlaufs                              FEHLER
STR-03  Signalgruppe im Programm ohne Freigabe                       WARNUNG
STR-04  Konfliktpaar nur in einer Richtung definiert                 WARNUNG
STR-05  Konfliktgeometrie mit unbekannter Signalgruppe               FEHLER
STR-06  Freigaben derselben Signalgruppe überschneiden sich          FEHLER
UZ-01   Umlaufzeit außerhalb des üblichen Bereichs                   WARNUNG
MF-01   Mindestfreigabezeit unterschritten                           FEHLER
KF-01   Feindliche Signalgruppen gleichzeitig freigegeben            FEHLER
ZZ-01   Zwischenzeit unterschritten                                  FEHLER
GZ-01   Gelbzeit passt nicht zur zulässigen Geschwindigkeit (Kfz)    FEHLER
GZ-02   Rot-Gelb-Zeit abweichend (Kfz)                               FEHLER
GZ-03   Gelb/Rot-Gelb bei Fußgängersignal                            WARNUNG
GZ-04   Keine Gelbzeit-Vorgabe für diese Geschwindigkeit             WARNUNG
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import zyklus
from .modell import GreenInterval, Junction, SignalProgram
from .zwischenzeiten import IntergreenCalc, intergreen_matrix

FEHLER, WARNUNG = "FEHLER", "WARNUNG"


@dataclass(frozen=True)
class Finding:
    level: str
    rule: str
    groups: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class IntergreenCheck:
    """Nachweis eines Übergangs räumend -> einfahrend im Programm."""
    clearing: str
    entering: str
    clearing_end: int | None
    entering_start: int
    required_s: int
    actual_s: int | None        # None bei gleichzeitiger Freigabe (Konflikt)

    @property
    def ok(self) -> bool:
        return self.actual_s is not None and self.actual_s >= self.required_s

    @property
    def status(self) -> str:
        if self.actual_s is None:
            return "KONFLIKT"
        return "OK" if self.ok else "NICHT EINGEHALTEN"


@dataclass
class ProgramResult:
    junction: Junction
    program: SignalProgram
    matrix: dict[tuple[str, str], IntergreenCalc]
    findings: list[Finding] = field(default_factory=list)
    intergreen_checks: list[IntergreenCheck] = field(default_factory=list)
    conflict_seconds: dict[tuple[str, str], set[int]] = field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == FEHLER]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARNUNG]

    @property
    def passed(self) -> bool:
        return not self.errors

    def greens_of(self, group: str) -> list[GreenInterval]:
        return [g for g in self.program.greens if g.group == group]

    def green_seconds(self, group: str) -> set[int]:
        cycle = self.program.cycle_s
        secs: set[int] = set()
        for g in self.greens_of(group):
            secs |= zyklus.seconds(g.start, g.end, cycle)
        return secs


# --------------------------------------------------------------------------- #
# Einzelprüfungen
# --------------------------------------------------------------------------- #

def _check_structure(res: ProgramResult) -> None:
    j, p, cycle = res.junction, res.program, res.program.cycle_s

    for g in p.greens:
        if g.group not in j.groups:
            res.findings.append(Finding(FEHLER, "STR-01", (g.group,),
                f"Signalgruppe '{g.group}' (Zeile {g.line}) ist nicht in signalgruppen.csv definiert."))
        for label, t in (("Freigabebeginn", g.start), ("Freigabeende", g.end)):
            if not 0 <= t <= cycle:
                res.findings.append(Finding(FEHLER, "STR-02", (g.group,),
                    f"{label} {t} s von {g.group} (Zeile {g.line}) liegt außerhalb "
                    f"des Umlaufs 0…{cycle} s."))

    used = {g.group for g in p.greens}
    for gid in j.groups:
        if gid not in used:
            res.findings.append(Finding(WARNUNG, "STR-03", (gid,),
                f"Signalgruppe {gid} erhält im Programm {p.id} keine Freigabe."))

    keys = {(c.clearing, c.entering) for c in j.conflicts}
    for c in j.conflicts:
        unknown = [x for x in (c.clearing, c.entering) if x not in j.groups]
        if unknown:
            res.findings.append(Finding(FEHLER, "STR-05", tuple(unknown),
                f"Konfliktgeometrie {c.clearing} -> {c.entering} verweist auf unbekannte "
                f"Signalgruppe(n): {', '.join(unknown)}."))
        elif (c.entering, c.clearing) not in keys:
            res.findings.append(Finding(WARNUNG, "STR-04", (c.clearing, c.entering),
                f"Konflikt {c.clearing} -> {c.entering} ist definiert, die Gegenrichtung "
                f"{c.entering} -> {c.clearing} fehlt."))

    for gid in used & set(j.groups):
        intervals = res.greens_of(gid)
        for a in range(len(intervals)):
            for b in range(a + 1, len(intervals)):
                ia, ib = intervals[a], intervals[b]
                overlap = (zyklus.seconds(ia.start, ia.end, cycle)
                           & zyklus.seconds(ib.start, ib.end, cycle))
                if overlap:
                    res.findings.append(Finding(FEHLER, "STR-06", (gid,),
                        f"Freigaben von {gid} (Zeilen {ia.line} und {ib.line}) überschneiden sich."))


def _check_cycle(res: ProgramResult) -> None:
    low, high = res.junction.parameters["umlaufzeit_bereich_s"]
    cycle = res.program.cycle_s
    if not low <= cycle <= high:
        res.findings.append(Finding(WARNUNG, "UZ-01", (),
            f"Umlaufzeit {cycle} s liegt außerhalb des üblichen Bereichs {low}…{high} s."))


def _check_min_green(res: ProgramResult) -> None:
    j, cycle = res.junction, res.program.cycle_s
    for g in res.program.greens:
        group = j.groups.get(g.group)
        if group is None:
            continue
        required = group.min_green_s
        if required is None:
            required = j.parameters["verkehrsarten"][group.typ]["mindestfreigabezeit_s"]
        actual = zyklus.duration(g.start, g.end, cycle)
        if actual < required:
            res.findings.append(Finding(FEHLER, "MF-01", (g.group,),
                f"Freigabezeit von {g.group} ({g.start}–{g.end} s) beträgt {actual} s, "
                f"gefordert sind mindestens {required} s."))


def _check_conflicts_and_intergreens(res: ProgramResult) -> None:
    cycle = res.program.cycle_s
    reported_pairs: set[frozenset[str]] = set()

    for (clearing, entering), calc in sorted(res.matrix.items()):
        clearing_greens = res.greens_of(clearing)
        entering_greens = res.greens_of(entering)
        if not clearing_greens or not entering_greens:
            continue

        # KF-01: gleichzeitige Freigabe feindlicher Signalgruppen
        overlap = res.green_seconds(clearing) & res.green_seconds(entering)
        pair = frozenset((clearing, entering))
        if overlap and pair not in reported_pairs:
            reported_pairs.add(pair)
            a, b = sorted(pair)
            res.conflict_seconds[(a, b)] = overlap
            spans = ", ".join(f"{s}–{s + n} s" for s, n in zyklus.blocks(overlap, cycle))
            res.findings.append(Finding(FEHLER, "KF-01", (a, b),
                f"Feindliche Signalgruppen {a} und {b} sind gleichzeitig freigegeben "
                f"({spans}, insgesamt {len(overlap)} s)."))

        # ZZ-01: Zwischenzeit vom letzten Freigabeende der räumenden Gruppe
        #        bis zu jedem Freigabebeginn der einfahrenden Gruppe
        clearing_secs = res.green_seconds(clearing)
        for eg in entering_greens:
            entering_secs = zyklus.seconds(eg.start, eg.end, cycle)
            if entering_secs & clearing_secs:
                res.intergreen_checks.append(IntergreenCheck(
                    clearing, entering, None, eg.start, calc.required_s, None))
                continue
            last_end, actual = min(
                ((cg.end % cycle, zyklus.gap(cg.end, eg.start, cycle)) for cg in clearing_greens),
                key=lambda item: item[1],
            )
            check = IntergreenCheck(clearing, entering, last_end, eg.start,
                                    calc.required_s, actual)
            res.intergreen_checks.append(check)
            if not check.ok:
                res.findings.append(Finding(FEHLER, "ZZ-01", (clearing, entering),
                    f"Zwischenzeit {clearing} → {entering} nicht eingehalten: vorhanden "
                    f"{actual} s (Freigabeende {clearing} bei {last_end} s, Freigabebeginn "
                    f"{entering} bei {eg.start} s), erforderlich {calc.required_s} s, "
                    f"Fehlbetrag {calc.required_s - actual} s."))


def _required_amber(speed_kmh: float, table: dict[str, int]) -> int | None:
    for limit in sorted(table, key=float):
        if speed_kmh <= float(limit):
            return int(table[limit])
    return None


def _check_amber(res: ProgramResult) -> None:
    params = res.junction.parameters
    for group in res.junction.groups.values():
        if group.typ == "Kfz":
            if group.speed_kmh is not None:
                required = _required_amber(group.speed_kmh, params["gelbzeit_kfz_nach_vzul_kmh"])
                if required is None:
                    res.findings.append(Finding(WARNUNG, "GZ-04", (group.id,),
                        f"Für v_zul = {group.speed_kmh:g} km/h ({group.id}) ist keine "
                        f"Gelbzeit hinterlegt – bitte manuell prüfen."))
                elif group.amber_s != required:
                    res.findings.append(Finding(FEHLER, "GZ-01", (group.id,),
                        f"Gelbzeit von {group.id} beträgt {group.amber_s} s, bei "
                        f"v_zul = {group.speed_kmh:g} km/h sind {required} s vorgesehen."))
            required_ra = params["rotgelbzeit_kfz_s"]
            if group.red_amber_s != required_ra:
                res.findings.append(Finding(FEHLER, "GZ-02", (group.id,),
                    f"Rot-Gelb-Zeit von {group.id} beträgt {group.red_amber_s} s, "
                    f"vorgesehen sind {required_ra} s."))
        elif group.typ == "Fg" and (group.amber_s or group.red_amber_s):
            res.findings.append(Finding(WARNUNG, "GZ-03", (group.id,),
                f"Fußgängersignal {group.id} hat Gelb/Rot-Gelb-Zeiten "
                f"({group.amber_s} s / {group.red_amber_s} s) – Fußgängersignale sind "
                f"üblicherweise zweifeldrig (Rot/Grün)."))


# --------------------------------------------------------------------------- #
# Gesamtprüfung
# --------------------------------------------------------------------------- #

_ORDER = {FEHLER: 0, WARNUNG: 1}


def check_program(junction: Junction, program_id: str) -> ProgramResult:
    program = junction.programs[program_id]
    res = ProgramResult(junction, program, intergreen_matrix(junction))
    _check_structure(res)
    _check_cycle(res)
    _check_min_green(res)
    _check_conflicts_and_intergreens(res)
    _check_amber(res)
    res.findings.sort(key=lambda f: (_ORDER[f.level], f.rule, f.groups))
    return res
