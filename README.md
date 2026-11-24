# LSA-Plancheck – automatisierte Plausibilitätsprüfung von Signalzeitenplänen

[![Tests](https://github.com/SohaibAhmedbhai/lsa-plancheck/actions/workflows/tests.yml/badge.svg)](https://github.com/SohaibAhmedbhai/lsa-plancheck/actions/workflows/tests.yml)
[![Live-Demo](https://img.shields.io/badge/Live--Demo-ansehen-1f6feb)](https://sohaibahmedbhai.github.io/lsa-plancheck/)

**▶ Live-Demo ohne Installation: [sohaibahmedbhai.github.io/lsa-plancheck/](https://sohaibahmedbhai.github.io/lsa-plancheck/)** – Beispielberichte und
Signalzeitenpläne direkt im Browser.

Python-Werkzeug, das Signalprogramme von Lichtsignalanlagen (LSA) automatisch prüft und einen
Prüfbericht als Teil der Dokumentation erzeugt. Geprüft werden **Konfliktfreiheit,
Zwischenzeiten, Mindestfreigabezeiten sowie Gelb- und Rot-Gelb-Zeiten**. Fehler werden mit
Ist- und Sollwert gemeldet und im Signalzeitenplan markiert.

![Signalzeitenplan eines fehlerhaften Entwurfs mit markierten Verstößen](https://sohaibahmedbhai.github.io/lsa-plancheck/signalzeitenplan_P2.png)

## Motivation

Bevor ein Signalprogramm in das Steuergerät übertragen und abgenommen wird, muss es auf
sicherheitsrelevante Fehler geprüft werden. Bei vielen Knotenpunkten und Programmvarianten ist
die Prüfung von Hand aufwendig und fehleranfällig. Dieses Werkzeug automatisiert die
Standardprüfungen und erzeugt eine nachvollziehbare Prüfdokumentation mit Rechenweg.

## Funktionen

- **Zwischenzeitenmatrix** aus der Konfliktgeometrie nach t<sub>z</sub> = t<sub>ü</sub> + t<sub>r</sub> − t<sub>e</sub>
  (alle Kennwerte in einer Parameterdatei, projektbezogen anpassbar)
- **Prüfung jedes Signalprogramms** mit 14 Regeln (siehe unten), auch für Freigaben über das
  Umlaufende hinaus
- **Signalzeitenplan als Grafik** mit Rot, Rot-Gelb, Grün und Gelb; Verstöße werden markiert
- **Prüfbericht** als eigenständige HTML-Datei, als Markdown und als JSON (maschinenlesbar)
- **Kommandozeile mit Rückgabewerten** (0 = fehlerfrei, 1 = Fehler, 2 = Eingabefehler),
  dadurch einsetzbar in automatisierten Abläufen
- Eingabe als **CSV-Dateien (Semikolon, Excel-kompatibel)**, deutsches Dezimalkomma erlaubt
- **17 automatisierte Tests** (pytest), u. a. Handrechnungen der Zwischenzeiten

## Prüfregeln

| Regel  | Prüfung                                                     | Stufe   |
|--------|-------------------------------------------------------------|---------|
| KF-01  | Feindliche Signalgruppen gleichzeitig freigegeben           | Fehler  |
| ZZ-01  | Zwischenzeit unterschritten                                 | Fehler  |
| MF-01  | Mindestfreigabezeit unterschritten                          | Fehler  |
| GZ-01  | Gelbzeit passt nicht zur zulässigen Geschwindigkeit (Kfz)   | Fehler  |
| GZ-02  | Rot-Gelb-Zeit abweichend (Kfz)                              | Fehler  |
| STR-01 | Unbekannte Signalgruppe im Programm                         | Fehler  |
| STR-02 | Zeitpunkt außerhalb des Umlaufs                             | Fehler  |
| STR-05 | Konfliktgeometrie mit unbekannter Signalgruppe              | Fehler  |
| STR-06 | Überschneidende Freigaben derselben Signalgruppe            | Fehler  |
| STR-03 | Signalgruppe erhält keine Freigabe                          | Warnung |
| STR-04 | Konfliktpaar nur in einer Richtung definiert                | Warnung |
| UZ-01  | Umlaufzeit außerhalb des üblichen Bereichs                  | Warnung |
| GZ-03  | Gelb/Rot-Gelb bei Fußgängersignal                           | Warnung |
| GZ-04  | Keine Gelbzeit-Vorgabe für die Geschwindigkeit hinterlegt   | Warnung |

## Berechnung der Zwischenzeiten

```
t_z = t_ü + t_r − t_e          (aufgerundet auf volle Sekunden)

t_r = (s_r + l_Fz) / v_r       Räumzeit
t_e = s_e / v_e                Einfahrzeit
```

| Größe | Bedeutung |
|---|---|
| t<sub>ü</sub> | Überfahrzeit der räumenden Verkehrsart |
| s<sub>r</sub> | Räumweg: Haltlinie der räumenden Gruppe bis Ende der Konfliktfläche |
| s<sub>e</sub> | Einfahrweg: Haltlinie der einfahrenden Gruppe bis Beginn der Konfliktfläche |
| l<sub>Fz</sub> | Fahrzeuglänge |
| v<sub>r</sub>, v<sub>e</sub> | Räum- bzw. Einfahrgeschwindigkeit |

### Kennwerte (nach RiLSA 2015)

| Verkehrsart / Bewegung | t<sub>ü</sub> [s] | v<sub>r</sub> [m/s] | l<sub>Fz</sub> [m] | v<sub>e</sub> [m/s] |
|---|---|---|---|---|
| Kfz geradeaus (`geradeaus`) | 3 | 10 | 6 | 11,1 |
| Kfz abbiegend, Radius ≥ 10 m (`abbiegend`) | 2 | 7 | 6 | 11,1 |
| Kfz abbiegend, Radius < 10 m (`abbiegend_eng`) | 2 | 5 | 6 | 11,1 |
| Radverkehr | 1 | 4 | 0 | 5 |
| Fußverkehr | 0 | 1,2 (zulässig 1,0–1,5) | 0 | 1,5 |

Weitere Vorgaben: Mindestfreigabezeit 5 s · Gelbzeit Kfz 3 / 4 / 5 s bei 50 / 60 / 70 km/h ·
Rot-Gelb 1 s · Zwischenzeiten werden stets aufgerundet.

Alle Werte stehen in [`lsa_pruefung/rilsa_parameter.json`](lsa_pruefung/rilsa_parameter.json).
Eine Datei `parameter.json` im Projektordner überschreibt einzelne Werte (z. B. 1,0 m/s für
Fußgänger an Seniorenstandorten). Für einzelne Konfliktpaare kann eine Zwischenzeit auch fest
vorgegeben werden (Spalte `zwischenzeit_vorgabe_s`). Im Beispielprojekt ist der Einfahrweg von
Fußgängern als sichere Annahme mit 0 m angesetzt (keine Einfahrzeit).

### Quellen der Kennwerte

Die Werte wurden im November 2026 mit diesen öffentlich zugänglichen Quellen abgeglichen. Für
den Einsatz an einer realen Anlage gilt der Originaltext der RiLSA (FGSV, Ausgabe 2015).

- [Wikipedia: Zwischenzeit (Verkehrstechnik)](https://de.wikipedia.org/wiki/Zwischenzeit_(Verkehrstechnik)) – Formel, Räum- und Einfahrgeschwindigkeiten, Aufrundung
- [ampelfan.de: Planung einer Lichtsignalanlage](http://www.ampelfan.de/Seiten_de/Seiten/signalprogramm7.htm) – Kfz-Werte geradeaus und abbiegend
- [BASt-Bericht V 356](https://edocs.tib.eu/files/e01fn22/1794972609.pdf) – Fußverkehr, Mindestfreigabezeit 5 s
- [bussgeldkatalog.org: Lichtzeichenanlage](https://www.bussgeldkatalog.org/lichtzeichenanlage/) – Gelbzeiten nach VwV-StVO zu § 37

## Installation und Nutzung

Voraussetzung: Python ≥ 3.10

```bash
pip install -r requirements.txt

# Zwischenzeitenmatrix berechnen
python -m lsa_pruefung matrix beispiele/knoten_hauptstrasse_ringstrasse -o ausgabe

# alle Programme prüfen, Berichte nach ./ausgabe schreiben
python -m lsa_pruefung pruefe beispiele/knoten_hauptstrasse_ringstrasse -o ausgabe

# nur ein Programm prüfen
python -m lsa_pruefung pruefe beispiele/knoten_hauptstrasse_ringstrasse -p P1

# Tests ausführen
python -m pytest
```

Beispielausgabe auf der Kommandozeile:

```
Programm P1 (t_U = 70 s): BESTANDEN – 0 Fehler, 0 Warnungen

Programm P2 (t_U = 70 s): NICHT BESTANDEN – 7 Fehler, 1 Warnungen
  [FEHLER ] KF-01: Feindliche Signalgruppen K1 und K4 sind gleichzeitig freigegeben (34–36 s, insgesamt 2 s).
  [FEHLER ] MF-01: Freigabezeit von F1 (43–46 s) beträgt 3 s, gefordert sind mindestens 5 s.
  [FEHLER ] ZZ-01: Zwischenzeit K2 → K3 nicht eingehalten: vorhanden 4 s (...), erforderlich 6 s, Fehlbetrag 2 s.
  ...
```

## Eingabeformat

Ein Projektordner beschreibt einen Knotenpunkt:

| Datei | Inhalt |
|---|---|
| `knoten.json` | Name, Ort, Liste der Signalprogramme mit Umlaufzeit und Datei |
| `signalgruppen.csv` | `id; typ; bezeichnung; v_zul_kmh; gelb_s; rotgelb_s; mindestfreigabe_s` |
| `konfliktgeometrie.csv` | `raeumend; einfahrend; raeumweg_m; einfahrweg_m; bewegung; zwischenzeit_vorgabe_s` (`bewegung` = `geradeaus`, `abbiegend` oder `abbiegend_eng`) |
| `signalprogramm_*.csv` | `signalgruppe; gruen_beginn_s; gruen_ende_s` (mehrere Zeilen je Gruppe möglich) |
| `parameter.json` | optional, überschreibt Kennwerte |

Zeilen, die mit `#` beginnen, sind Kommentare. Leeres Feld `mindestfreigabe_s` bedeutet:
Standardwert der Verkehrsart.

## Beispielprojekt

[`beispiele/knoten_hauptstrasse_ringstrasse`](beispiele/knoten_hauptstrasse_ringstrasse) ist ein
**fiktiver** vierarmiger Knotenpunkt mit 4 Kfz- und 4 Fußgänger-Signalgruppen und 24
Konfliktbeziehungen:

- **P1** – korrektes 2-Phasen-Programm (t<sub>U</sub> = 70 s), Freigaben teilweise über das
  Umlaufende hinaus → *bestanden*
- **P2** – Entwurf mit eingebauten Fehlern (gleichzeitige Freigabe, zu kurze Zwischenzeiten,
  zu kurze Fußgängerfreigabe, Gruppe ohne Freigabe) → *7 Fehler, 1 Warnung*

Die erzeugten Berichte stehen in der [Live-Demo](https://sohaibahmedbhai.github.io/lsa-plancheck/): [Prüfbericht P1](https://sohaibahmedbhai.github.io/lsa-plancheck/pruefbericht_P1.html) · [Prüfbericht P2](https://sohaibahmedbhai.github.io/lsa-plancheck/pruefbericht_P2.html). Sie werden bei jedem Push von GitHub Actions neu erzeugt (`.github/workflows/pages.yml`).

## Aufbau

```
lsa_pruefung/
├── modell.py            Datenmodell, Einlesen und Validierung der Eingaben
├── zwischenzeiten.py    Zwischenzeitenberechnung und -matrix
├── zyklus.py            Zeitrechnung im Umlauf (Freigaben über das Umlaufende)
├── pruefungen.py        Prüfregeln
├── diagramm.py          Signalzeitenplan (matplotlib)
├── bericht.py           Prüfbericht HTML / Markdown / JSON
├── cli.py               Kommandozeile
└── rilsa_parameter.json Kennwerte je Verkehrsart
tests/                   pytest
site/index.html          Startseite der Live-Demo (GitHub Pages)
```

## Grenzen und Ausblick

- Bedingt verträgliche Ströme (z. B. Abbieger mit parallelem Fußgängerverkehr) werden als
  verträglich behandelt; nur feindliche Paare werden geprüft.
- Geprüft werden Festzeitprogramme. Verkehrsabhängige Logik (z. B. VS-PLUS-Parameter) und
  Programmwechsel sind nicht enthalten.
- Ausbaustufen: Import von Planungsdaten aus LISA+, Prüfung von Umschaltvorgängen,
  Plausibilität verkehrsabhängiger Parameter, Anbindung an Steuergeräte über OCIT-Outstations.

## Haftungsausschluss

Lern- und Portfolioprojekt. Das Werkzeug unterstützt die Prüfung, ersetzt aber nicht die
Verantwortung und Prüfung durch eine Fachplanerin bzw. einen Fachplaner.

---

Autor: Sohaib Ahmed · Lizenz: MIT
