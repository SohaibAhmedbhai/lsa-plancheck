"""Signalzeitenplan als Diagramm (Rot, Rot-Gelb, Grün, Gelb je Signalgruppe).

Verletzte Zwischenzeiten und gleichzeitige Freigaben feindlicher
Signalgruppen werden im Diagramm rot markiert.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from . import zyklus  # noqa: E402
from .pruefungen import ProgramResult  # noqa: E402

COLORS = {
    "gruen": "#2e9e44",
    "gelb": "#f2b705",
    "rotgelb": "#f08c00",
    "rot": "#d62828",
    "fehler": "#c1121f",
}


LABEL = dict(fontsize=6.5, color=COLORS["fehler"],
             bbox=dict(facecolor="white", edgecolor="none", pad=0.6, alpha=0.9))


def _states(res: ProgramResult, gid: str) -> dict[str, set[int]]:
    cycle = res.program.cycle_s
    group = res.junction.groups[gid]
    green = res.green_seconds(gid)
    amber: set[int] = set()
    red_amber: set[int] = set()
    for g in res.greens_of(gid):
        amber |= {(g.end + k) % cycle for k in range(group.amber_s)}
        red_amber |= {(g.start - 1 - k) % cycle for k in range(group.red_amber_s)}
    amber -= green
    red_amber -= green | amber
    red = set(range(cycle)) - green - amber - red_amber
    return {"gruen": green, "gelb": amber, "rotgelb": red_amber, "rot": red}


def plot_program(res: ProgramResult, path: str | Path) -> Path:
    path = Path(path)
    cycle = res.program.cycle_s
    group_ids = list(res.junction.groups)
    rows = {gid: len(group_ids) - 1 - i for i, gid in enumerate(group_ids)}

    fig_h = 1.2 + 0.42 * len(group_ids)
    fig, ax = plt.subplots(figsize=(11, fig_h), dpi=150)

    for gid, y in rows.items():
        states = _states(res, gid)
        for state, height in (("rot", 0.18), ("rotgelb", 0.5), ("gelb", 0.5), ("gruen", 0.5)):
            bars = zyklus.blocks(states[state], cycle)
            if bars:
                ax.broken_barh(bars, (y - height / 2, height), facecolors=COLORS[state],
                               edgecolor="none")
        for g in res.greens_of(gid):
            dur = zyklus.duration(g.start, g.end, cycle)
            mid = (g.start + dur / 2) % cycle
            ax.text(mid, y, str(dur), ha="center", va="center", fontsize=7, color="white",
                    fontweight="bold")

    # Gleichzeitige Freigabe feindlicher Gruppen: schraffieren
    for (a, b), secs in res.conflict_seconds.items():
        for gid in (a, b):
            ax.broken_barh(zyklus.blocks(secs, cycle), (rows[gid] - 0.3, 0.6),
                           facecolors="none", edgecolor=COLORS["fehler"], hatch="////",
                           linewidth=1.2)

    # Nicht eingehaltene Zwischenzeiten: Klammer in der Zeile der einfahrenden Gruppe
    #    (mehrere Verstöße mit gleicher Klammer werden in einer Beschriftung gebündelt)
    brackets: dict[tuple[str, int, int], list[str]] = {}
    for chk in res.intergreen_checks:
        if chk.actual_s is None or chk.ok:
            continue
        key = (chk.entering, chk.clearing_end, chk.clearing_end + chk.actual_s)
        brackets.setdefault(key, []).append(
            f"{chk.clearing}→{chk.entering} {chk.actual_s}/{chk.required_s} s")
    for (entering, start, end), labels in brackets.items():
        y = rows[entering] + 0.36
        # über das Umlaufende hinaus: in zwei Teilen zeichnen
        segments = [(start, min(end, cycle))] + ([(0, end - cycle)] if end > cycle else [])
        for x0, x1 in segments:
            ax.annotate("", xy=(x1, y), xytext=(x0, y),
                        arrowprops=dict(arrowstyle="|-|", color=COLORS["fehler"], lw=1.1,
                                        shrinkA=0, shrinkB=0, mutation_scale=3))
        text = "tz ist/soll: " + ", ".join(labels)
        if start > cycle * 0.6:   # Beschriftung links der Klammer, damit sie im Bild bleibt
            ax.text(start - 0.4, y, text, va="center", ha="right", **LABEL)
        else:
            ax.text(segments[-1][1] + 0.4, y, text, va="center", ha="left", **LABEL)

    # Unterschrittene Mindestfreigabezeiten: Grünbalken rot umranden
    too_short = {f.groups[0] for f in res.findings if f.rule == "MF-01"}
    for gid in too_short:
        for g in res.greens_of(gid):
            for x0, w in zyklus.blocks(zyklus.seconds(g.start, g.end, cycle), cycle):
                ax.broken_barh([(x0, w)], (rows[gid] - 0.3, 0.6), facecolors="none",
                               edgecolor=COLORS["fehler"], linewidth=1.6)
            ax.text(g.end % cycle + 0.6, rows[gid], "Mindestfreigabezeit unterschritten",
                    va="center", ha="left", **LABEL)

    ax.set_yticks(list(rows.values()))
    ax.set_yticklabels([f"{gid}  {res.junction.groups[gid].name}" for gid in rows], fontsize=8)
    ax.set_xlim(0, cycle)
    ax.set_ylim(-0.7, len(group_ids) - 0.3)
    step = 5 if cycle <= 120 else 10
    ax.set_xticks(range(0, cycle + 1, step))
    ax.tick_params(axis="x", labelsize=8)
    ax.set_xlabel("Zeit im Umlauf [s]", fontsize=9)
    ax.grid(axis="x", color="#dddddd", linewidth=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    status = "BESTANDEN" if res.passed else f"NICHT BESTANDEN ({len(res.errors)} Fehler)"
    ax.set_title(f"Signalzeitenplan {res.program.id} – {res.junction.name}  |  "
                 f"t_U = {cycle} s  |  {status}", fontsize=10, loc="left")

    legend = [Patch(color=COLORS["gruen"], label="Grün"),
              Patch(color=COLORS["gelb"], label="Gelb"),
              Patch(color=COLORS["rotgelb"], label="Rot-Gelb"),
              Patch(color=COLORS["rot"], label="Rot")]
    if res.conflict_seconds:
        legend.append(Patch(facecolor="none", edgecolor=COLORS["fehler"], hatch="////",
                            label="Konflikt"))
    ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.1 - 0.5 / fig_h),
              ncol=len(legend), fontsize=8, frameon=False)

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path
