"""Prüfbericht als HTML (eigenständig, Diagramm eingebettet), Markdown und JSON."""

from __future__ import annotations

import base64
import html
import json
from datetime import date
from pathlib import Path

from . import __version__, zyklus
from .pruefungen import ProgramResult

RULE_TITLES = {
    "STR-01": "Unbekannte Signalgruppe im Programm",
    "STR-02": "Zeitpunkt außerhalb des Umlaufs",
    "STR-03": "Signalgruppe ohne Freigabe",
    "STR-04": "Konfliktpaar nur einseitig definiert",
    "STR-05": "Konfliktgeometrie mit unbekannter Gruppe",
    "STR-06": "Überschneidende Freigaben einer Gruppe",
    "UZ-01": "Umlaufzeit",
    "MF-01": "Mindestfreigabezeit",
    "KF-01": "Konfliktfreiheit",
    "ZZ-01": "Zwischenzeit",
    "GZ-01": "Gelbzeit",
    "GZ-02": "Rot-Gelb-Zeit",
    "GZ-03": "Gelb bei Fußgängersignal",
    "GZ-04": "Gelbzeit-Vorgabe fehlt",
}


def _fmt(x: float | None, digits: int = 2) -> str:
    return "–" if x is None else f"{x:.{digits}f}".replace(".", ",")


def _summary(res: ProgramResult) -> dict:
    checks = res.intergreen_checks
    return {
        "status": "BESTANDEN" if res.passed else "NICHT BESTANDEN",
        "fehler": len(res.errors),
        "warnungen": len(res.warnings),
        "zwischenzeiten_geprueft": len(checks),
        "zwischenzeiten_ok": sum(c.ok for c in checks),
    }


def _green_rows(res: ProgramResult) -> list[list[str]]:
    rows = []
    cycle = res.program.cycle_s
    for gid, group in res.junction.groups.items():
        greens = res.greens_of(gid)
        if not greens:
            rows.append([gid, group.name, group.typ, "–", "–", "0"])
        for g in greens:
            rows.append([gid, group.name, group.typ, str(g.start), str(g.end),
                         str(zyklus.duration(g.start, g.end, cycle))])
    return rows


def _matrix_table(res: ProgramResult) -> tuple[list[str], list[list[str]]]:
    ids = list(res.junction.groups)
    header = ["räumend \\ einfahrend"] + ids
    rows = []
    for a in ids:
        row = [a]
        for b in ids:
            calc = res.matrix.get((a, b))
            row.append("" if calc is None else str(calc.required_s))
        rows.append(row)
    return header, rows


def _calc_rows(res: ProgramResult) -> list[list[str]]:
    rows = []
    for (a, b), c in sorted(res.matrix.items()):
        rows.append([a, b, _fmt(c.t_ue, 1), _fmt(c.t_r), _fmt(c.t_e), _fmt(c.exact_s),
                     str(c.required_s), c.source])
    return rows


def _check_rows(res: ProgramResult) -> list[list[str]]:
    rows = []
    for c in sorted(res.intergreen_checks, key=lambda c: (c.ok, c.clearing, c.entering)):
        rows.append([c.clearing, c.entering,
                     "–" if c.clearing_end is None else str(c.clearing_end),
                     str(c.entering_start),
                     "–" if c.actual_s is None else str(c.actual_s),
                     str(c.required_s), c.status])
    return rows


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #

def write_json(res: ProgramResult, path: str | Path) -> Path:
    path = Path(path)
    data = {
        "knoten": res.junction.name,
        "programm": res.program.id,
        "umlaufzeit_s": res.program.cycle_s,
        "werkzeug_version": __version__,
        "zusammenfassung": _summary(res),
        "befunde": [{"stufe": f.level, "regel": f.rule, "signalgruppen": list(f.groups),
                     "meldung": f.message} for f in res.findings],
        "zwischenzeiten": [{"raeumend": c.clearing, "einfahrend": c.entering,
                            "erforderlich_s": c.required_s, "vorhanden_s": c.actual_s,
                            "status": c.status} for c in res.intergreen_checks],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #

def _md_table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def write_markdown(res: ProgramResult, path: str | Path, image_name: str | None) -> Path:
    path = Path(path)
    s = _summary(res)
    j, p = res.junction, res.program
    parts = [
        f"# Prüfbericht Signalprogramm {p.id}",
        "",
        f"**Knotenpunkt:** {j.name}  ",
        f"**Ort:** {j.location or '–'}  ",
        f"**Programm:** {p.id} – {p.description or '–'}  ",
        f"**Umlaufzeit:** {p.cycle_s} s  ",
        f"**Prüfdatum:** {date.today():%d.%m.%Y}  ",
        f"**Werkzeug:** lsa_pruefung {__version__}",
        "",
        f"## Ergebnis: {s['status']}",
        "",
        f"- Fehler: {s['fehler']}",
        f"- Warnungen: {s['warnungen']}",
        f"- Zwischenzeiten eingehalten: {s['zwischenzeiten_ok']} von {s['zwischenzeiten_geprueft']}",
        "",
    ]
    if image_name:
        parts += [f"![Signalzeitenplan]({image_name})", ""]
    parts += ["## Befunde", ""]
    if res.findings:
        parts.append(_md_table(["Stufe", "Regel", "Prüfung", "Meldung"],
                               [[f.level, f.rule, RULE_TITLES.get(f.rule, ""), f.message]
                                for f in res.findings]))
    else:
        parts.append("Keine Befunde.")
    parts += ["", "## Freigabezeiten", "",
              _md_table(["Gruppe", "Bezeichnung", "Art", "Beginn [s]", "Ende [s]", "Dauer [s]"],
                        _green_rows(res)),
              "", "## Zwischenzeitenmatrix [s]", "", _md_table(*_matrix_table(res)),
              "", "## Nachweis der Zwischenzeiten im Programm", "",
              _md_table(["räumend", "einfahrend", "Ende räumend", "Beginn einfahrend",
                         "vorhanden [s]", "erforderlich [s]", "Status"], _check_rows(res)),
              "", "## Rechenweg Zwischenzeiten (t_z = t_ü + t_r − t_e)", "",
              _md_table(["räumend", "einfahrend", "t_ü [s]", "t_r [s]", "t_e [s]",
                         "t_z exakt [s]", "t_z [s]", "Quelle"], _calc_rows(res)),
              "", "---",
              "*Automatisch erstellter Prüfbericht. Die verwendeten Kennwerte stehen in der "
              "Parameterdatei und sind vor der Anwendung mit der gültigen RiLSA-Ausgabe "
              "abzugleichen. Der Bericht ersetzt nicht die Prüfung durch eine Fachplanerin "
              "bzw. einen Fachplaner.*", ""]
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #

_CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1d2433;margin:0;background:#f5f6f8}
main{max-width:1080px;margin:0 auto;padding:28px 20px 48px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px;border-bottom:1px solid #dde1e7;padding-bottom:6px}
.meta{color:#5b6475;font-size:14px;line-height:1.6}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}
.card{background:#fff;border:1px solid #dde1e7;border-radius:8px;padding:12px 16px;min-width:150px}
.card b{display:block;font-size:22px}.card span{color:#5b6475;font-size:13px}
.ok{color:#1f7a35}.bad{color:#b3141f}.warn{color:#9a6700}
.status{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:600;font-size:14px;margin-top:12px}
.status.ok{background:#e3f4e7}.status.bad{background:#fde6e8}
table{border-collapse:collapse;width:100%;background:#fff;font-size:13px;border:1px solid #dde1e7}
th,td{border-bottom:1px solid #eceff3;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#eef1f5;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.matrix td,.matrix th{text-align:center}.matrix td:first-child,.matrix th:first-child{text-align:left;font-weight:600}
td:nth-child(2){white-space:nowrap}
.scroll{overflow-x:auto}
img{max-width:100%;background:#fff;border:1px solid #dde1e7;border-radius:8px}
.foot{color:#5b6475;font-size:12px;margin-top:32px}
"""


def _html_table(header: list[str], rows: list[list[str]], cls: str = "",
                num_cols: set[int] | None = None, status_col: int | None = None) -> str:
    num_cols = num_cols or set()
    out = [f'<div class="scroll"><table class="{cls}"><thead><tr>']
    out += [f'<th class="{"num" if i in num_cols else ""}">{html.escape(h)}</th>'
            for i, h in enumerate(header)]
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>")
        for i, cell in enumerate(r):
            classes = []
            if i in num_cols:
                classes.append("num")
            if i == status_col:
                classes.append({"OK": "ok", "FEHLER": "bad", "WARNUNG": "warn"}.get(cell, "bad"))
            out.append(f'<td class="{" ".join(classes)}">{html.escape(cell)}</td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def write_html(res: ProgramResult, path: str | Path, image_path: Path | None) -> Path:
    path = Path(path)
    s = _summary(res)
    j, p = res.junction, res.program
    status_cls = "ok" if res.passed else "bad"
    img = ""
    if image_path is not None and image_path.exists():
        data = base64.b64encode(image_path.read_bytes()).decode("ascii")
        img = f'<img alt="Signalzeitenplan {html.escape(p.id)}" src="data:image/png;base64,{data}">'

    findings = (_html_table(["Stufe", "Regel", "Prüfung", "Meldung"],
                            [[f.level, f.rule, RULE_TITLES.get(f.rule, ""), f.message]
                             for f in res.findings], status_col=0)
                if res.findings else '<p class="ok">Keine Befunde.</p>')

    body = f"""
<main>
<h1>Prüfbericht Signalprogramm {html.escape(p.id)}</h1>
<div class="meta">
Knotenpunkt: <b>{html.escape(j.name)}</b> · Ort: {html.escape(j.location or '–')}<br>
Programm: {html.escape(p.id)} – {html.escape(p.description or '–')} · Umlaufzeit t<sub>U</sub> = {p.cycle_s} s<br>
Prüfdatum: {date.today():%d.%m.%Y} · Werkzeug: lsa_pruefung {__version__}
</div>
<div class="status {status_cls}">{s['status']}</div>
<div class="cards">
 <div class="card"><b class="{'bad' if s['fehler'] else 'ok'}">{s['fehler']}</b><span>Fehler</span></div>
 <div class="card"><b class="{'warn' if s['warnungen'] else 'ok'}">{s['warnungen']}</b><span>Warnungen</span></div>
 <div class="card"><b>{s['zwischenzeiten_ok']} / {s['zwischenzeiten_geprueft']}</b><span>Zwischenzeiten eingehalten</span></div>
 <div class="card"><b>{len(j.groups)}</b><span>Signalgruppen</span></div>
</div>
<h2>Signalzeitenplan</h2>
{img}
<h2>Befunde</h2>
{findings}
<h2>Freigabezeiten</h2>
{_html_table(["Gruppe", "Bezeichnung", "Art", "Beginn [s]", "Ende [s]", "Dauer [s]"],
             _green_rows(res), num_cols={3, 4, 5})}
<h2>Zwischenzeitenmatrix [s]</h2>
{_html_table(*_matrix_table(res), cls="matrix")}
<h2>Nachweis der Zwischenzeiten im Programm</h2>
{_html_table(["räumend", "einfahrend", "Ende räumend [s]", "Beginn einfahrend [s]",
              "vorhanden [s]", "erforderlich [s]", "Status"], _check_rows(res),
             num_cols={2, 3, 4, 5}, status_col=6)}
<h2>Rechenweg Zwischenzeiten (t<sub>z</sub> = t<sub>ü</sub> + t<sub>r</sub> − t<sub>e</sub>)</h2>
{_html_table(["räumend", "einfahrend", "t_ü [s]", "t_r [s]", "t_e [s]", "t_z exakt [s]",
              "t_z [s]", "Quelle"], _calc_rows(res), num_cols={2, 3, 4, 5, 6})}
<p class="foot">Automatisch erstellter Prüfbericht. Die verwendeten Kennwerte stehen in der
Parameterdatei und sind vor der Anwendung mit der gültigen RiLSA-Ausgabe abzugleichen.
Der Bericht ersetzt nicht die Prüfung durch eine Fachplanerin bzw. einen Fachplaner.</p>
</main>"""

    doc = (f'<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f"<title>Prüfbericht {html.escape(p.id)} – {html.escape(j.name)}</title>"
           f"<style>{_CSS}</style></head><body>{body}</body></html>")
    path.write_text(doc, encoding="utf-8")
    return path
