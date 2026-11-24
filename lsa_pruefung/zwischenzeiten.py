"""Berechnung der Zwischenzeiten.

Die Zwischenzeit t_z ist die Zeit zwischen dem Freigabeende der räumenden
und dem Freigabebeginn der einfahrenden (feindlichen) Signalgruppe:

    t_z = t_ü + t_r - t_e

    t_ü  Überfahrzeit (Kfz geradeaus 3 s, Kfz abbiegend 2 s)
    t_r  Räumzeit      = (s_r + l_Fz) / v_r
    t_e  Einfahrzeit   = s_e / v_e

    s_r  Räumweg  (Haltlinie räumende Gruppe  -> Ende der Konfliktfläche)
    s_e  Einfahrweg (Haltlinie einfahrende Gruppe -> Beginn der Konfliktfläche)
    l_Fz Fahrzeuglänge, v_r Räumgeschwindigkeit, v_e Einfahrgeschwindigkeit

Das Ergebnis wird auf volle Sekunden aufgerundet. Die Kennwerte je
Verkehrsart stehen in ``rilsa_parameter.json`` und sind projektbezogen
anpassbar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .modell import ConflictGeometry, Junction


@dataclass(frozen=True)
class IntergreenCalc:
    clearing: str
    entering: str
    t_ue: float
    t_r: float
    t_e: float
    exact_s: float | None       # ungerundeter Wert (None bei fester Vorgabe)
    required_s: int             # maßgebende Zwischenzeit
    source: str                 # "berechnet" | "Vorgabe"

    @property
    def key(self) -> tuple[str, str]:
        return self.clearing, self.entering


def calculate(conflict: ConflictGeometry, junction: Junction) -> IntergreenCalc:
    groups = junction.groups
    kinds = junction.parameters["verkehrsarten"]
    clearing = groups[conflict.clearing]
    entering = groups[conflict.entering]
    pc, pe = kinds[clearing.typ], kinds[entering.typ]

    t_ue_param = pc["ueberfahrzeit_s"]  # Zahl oder je Bewegung (Kfz: Abbieger 2 s)
    t_ue = float(t_ue_param[conflict.clearing_movement] if isinstance(t_ue_param, dict)
                 else t_ue_param)
    v_r = float(pc["raeumgeschwindigkeit_ms"][conflict.clearing_movement])
    t_r = (conflict.clearing_distance_m + float(pc["fahrzeuglaenge_m"])) / v_r
    t_e = conflict.entering_distance_m / float(pe["einfahrgeschwindigkeit_ms"])
    exact = t_ue + t_r - t_e

    if conflict.intergreen_override_s is not None:
        return IntergreenCalc(conflict.clearing, conflict.entering, t_ue, t_r, t_e,
                              None, conflict.intergreen_override_s, "Vorgabe")

    required = max(0, math.ceil(round(exact, 6)))  # round() gegen Gleitkomma-Artefakte
    return IntergreenCalc(conflict.clearing, conflict.entering, t_ue, t_r, t_e,
                          exact, required, "berechnet")


def intergreen_matrix(junction: Junction) -> dict[tuple[str, str], IntergreenCalc]:
    """Zwischenzeitenmatrix: (räumend, einfahrend) -> Berechnung.

    Konfliktpaare mit unbekannten Signalgruppen werden übersprungen
    (die Strukturprüfung meldet sie als Fehler).
    """
    matrix = {}
    for conflict in junction.conflicts:
        if conflict.clearing in junction.groups and conflict.entering in junction.groups:
            calc = calculate(conflict, junction)
            matrix[calc.key] = calc
    return matrix
