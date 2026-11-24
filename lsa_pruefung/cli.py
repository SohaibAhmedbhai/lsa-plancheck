"""Kommandozeile.

    python -m lsa_pruefung pruefe <projektordner> [-p P1 -p P2] [-o ausgabe]
    python -m lsa_pruefung matrix <projektordner> [-o ausgabe]

Rückgabewerte: 0 = alle Programme fehlerfrei, 1 = Fehler gefunden,
2 = Eingabedaten unvollständig oder fehlerhaft. Damit lässt sich das
Werkzeug auch in automatisierte Abläufe (z. B. CI) einbinden.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import __version__
from .bericht import write_html, write_json, write_markdown
from .diagramm import plot_program
from .modell import InputError, load_junction
from .pruefungen import check_program
from .zwischenzeiten import intergreen_matrix


def _cmd_check(args: argparse.Namespace) -> int:
    junction = load_junction(args.projekt)
    program_ids = args.programm or list(junction.programs)
    unknown = [p for p in program_ids if p not in junction.programs]
    if unknown:
        raise InputError(f"Programm(e) nicht in knoten.json: {', '.join(unknown)}")

    out = Path(args.ausgabe)
    out.mkdir(parents=True, exist_ok=True)
    any_error = False
    print(f"Knotenpunkt: {junction.name}")
    for pid in program_ids:
        res = check_program(junction, pid)
        any_error |= not res.passed
        png = plot_program(res, out / f"signalzeitenplan_{pid}.png")
        write_markdown(res, out / f"pruefbericht_{pid}.md", png.name)
        write_html(res, out / f"pruefbericht_{pid}.html", png)
        write_json(res, out / f"pruefergebnis_{pid}.json")

        status = "BESTANDEN" if res.passed else "NICHT BESTANDEN"
        print(f"\nProgramm {pid} (t_U = {res.program.cycle_s} s): {status} – "
              f"{len(res.errors)} Fehler, {len(res.warnings)} Warnungen")
        for f in res.findings:
            print(f"  [{f.level:<7}] {f.rule}: {f.message}")
    print(f"\nBerichte gespeichert in: {out.resolve()}")
    return 1 if any_error else 0


def _cmd_matrix(args: argparse.Namespace) -> int:
    junction = load_junction(args.projekt)
    matrix = intergreen_matrix(junction)
    ids = list(junction.groups)
    out = Path(args.ausgabe)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "zwischenzeitenmatrix.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(["raeumend/einfahrend"] + ids)
        for a in ids:
            writer.writerow([a] + [matrix[(a, b)].required_s if (a, b) in matrix else ""
                                   for b in ids])
    width = max(len(i) for i in ids) + 2
    print("Zwischenzeitenmatrix [s] (Zeile = räumend, Spalte = einfahrend)\n")
    print(" " * width + "".join(f"{b:>{width}}" for b in ids))
    for a in ids:
        cells = "".join(f"{matrix[(a, b)].required_s if (a, b) in matrix else '·':>{width}}"
                        for b in ids)
        print(f"{a:<{width}}{cells}")
    print(f"\nGespeichert: {path.resolve()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lsa_pruefung",
        description="Plausibilitätsprüfung von Signalzeitenplänen für Lichtsignalanlagen.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="befehl", required=True)

    p_check = sub.add_parser("pruefe", help="Signalprogramme prüfen und Berichte erzeugen")
    p_check.add_argument("projekt", help="Projektordner mit knoten.json")
    p_check.add_argument("-p", "--programm", action="append",
                         help="nur dieses Programm prüfen (mehrfach möglich)")
    p_check.add_argument("-o", "--ausgabe", default="ausgabe", help="Ausgabeordner")
    p_check.set_defaults(func=_cmd_check)

    p_matrix = sub.add_parser("matrix", help="nur die Zwischenzeitenmatrix berechnen")
    p_matrix.add_argument("projekt", help="Projektordner mit knoten.json")
    p_matrix.add_argument("-o", "--ausgabe", default="ausgabe", help="Ausgabeordner")
    p_matrix.set_defaults(func=_cmd_matrix)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except InputError as exc:
        print(f"Eingabefehler: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
