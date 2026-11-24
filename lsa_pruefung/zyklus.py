"""Hilfsfunktionen für Zeiten im Umlauf (zyklische Zeitachse, 1-s-Raster).

Eine Freigabe läuft von ``start`` (einschließlich) bis ``end`` (ausschließlich).
Freigaben dürfen über das Umlaufende hinausgehen, z. B. 60 -> 10 bei t_U = 70.
"""

from __future__ import annotations


def duration(start: int, end: int, cycle: int) -> int:
    return (end - start) % cycle


def seconds(start: int, end: int, cycle: int) -> set[int]:
    """Alle vollen Sekunden, in denen die Freigabe aktiv ist."""
    return {(start + k) % cycle for k in range(duration(start, end, cycle))}


def gap(from_t: int, to_t: int, cycle: int) -> int:
    """Zeit von ``from_t`` vorwärts bis ``to_t`` im Umlauf."""
    return (to_t - from_t) % cycle


def blocks(secs: set[int], cycle: int) -> list[tuple[int, int]]:
    """Fasst Sekunden zu zusammenhängenden Blöcken (start, länge) zusammen.

    Blöcke über das Umlaufende werden in zwei Teile geteilt (für Diagramme).
    """
    result: list[tuple[int, int]] = []
    for t in range(cycle):
        if t in secs:
            if result and result[-1][0] + result[-1][1] == t:
                result[-1] = (result[-1][0], result[-1][1] + 1)
            else:
                result.append((t, 1))
    return result
