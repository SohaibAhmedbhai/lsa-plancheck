"""Schnittstelle für die interaktive Web-Prüfung (läuft im Browser über Pyodide).

Die Webseite übergibt die drei CSV-Dateien als Text, diese Funktion legt daraus
einen temporären Projektordner an, prüft das Signalprogramm und gibt das
Ergebnis als JSON-fähiges Dictionary zurück (Befunde, Diagramm, Prüfbericht).
"""

from __future__ import annotations

import base64
import json
import shutil
import tempfile
from pathlib import Path

from .bericht import RULE_TITLES, write_html
from .diagramm import plot_program
from .modell import InputError, load_junction
from .pruefungen import check_program


def pruefe_texte(signalgruppen_csv: str, konfliktgeometrie_csv: str, signalprogramm_csv: str,
                 umlaufzeit_s: int, name: str = "Eigener Knotenpunkt") -> dict:
    """Prüft ein Signalprogramm, das als CSV-Texte übergeben wird."""
    folder = Path(tempfile.mkdtemp(prefix="lsa_web_"))
    try:
        (folder / "signalgruppen.csv").write_text(signalgruppen_csv, encoding="utf-8")
        (folder / "konfliktgeometrie.csv").write_text(konfliktgeometrie_csv, encoding="utf-8")
        (folder / "signalprogramm.csv").write_text(signalprogramm_csv, encoding="utf-8")
        try:
            cycle = int(umlaufzeit_s)
        except (TypeError, ValueError):
            return {"fehler_eingabe": "Die Umlaufzeit muss eine ganze Zahl in Sekunden sein."}
        meta = {"name": name or "Eigener Knotenpunkt", "ort": "",
                "programme": [{"id": "P1", "umlaufzeit_s": cycle, "datei": "signalprogramm.csv",
                               "beschreibung": "Über die Webseite geprüftes Programm"}]}
        (folder / "knoten.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

        try:
            junction = load_junction(folder)
        except InputError as exc:
            return {"fehler_eingabe": str(exc)}

        res = check_program(junction, "P1")
        png = plot_program(res, folder / "signalzeitenplan.png")
        report = write_html(res, folder / "pruefbericht.html", png)
        return {
            "bestanden": res.passed,
            "fehler": len(res.errors),
            "warnungen": len(res.warnings),
            "signalgruppen": len(junction.groups),
            "konfliktpaare": len(res.matrix),
            "zwischenzeiten_ok": sum(c.ok for c in res.intergreen_checks),
            "zwischenzeiten_geprueft": len(res.intergreen_checks),
            "befunde": [{"stufe": f.level, "regel": f.rule, "pruefung": RULE_TITLES.get(f.rule, ""),
                         "meldung": f.message} for f in res.findings],
            "diagramm_png_base64": base64.b64encode(png.read_bytes()).decode("ascii"),
            "bericht_html": report.read_text(encoding="utf-8"),
        }
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def pruefe_json(*args) -> str:
    """Wie :func:`pruefe_texte`, aber als JSON-Text (für den Aufruf aus JavaScript)."""
    return json.dumps(pruefe_texte(*args), ensure_ascii=False)
