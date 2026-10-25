# Handoff: PDF-Report IFC2Print (Variante 2a «Datenblatt»)

Umsetzungsplan für Claude Code im Repo `GianBlaser/IFC2Print` (Branch `main`).
Schweizer Schreibweise im Code und in allen Texten: nie «ß».

## Überblick

Der heutige Report (`core/output/report.py`, Matplotlib) besteht aus einer Kennzahlen-Liste in Monospace-Schrift und drei Diagrammen ohne Aussage.
Neu ist er ein **Übergabeblatt für Architekturbüros** (Leser kennen IFC). Er beantwortet drei Fragen:

1. Kann man das Modell drucken? (Urteil)
2. Was hat das Tool am IFC verändert? (Regelwerk, Druckbarkeit je Klasse, Prüfpunkte)
3. Welche Bauteile sind betroffen? (Anhang Bauteiltabelle)

**Keine Kosten im Report.** Filament und Druckzeit kommen auch nicht vor.

## Über die Design-Datei

`PDF Report.dc.html` ist eine **Design-Referenz in HTML** und kein Produktionscode. Öffnen im Browser (mit `support.js` im selben Ordner) und zu **Abschnitt 2a** scrollen. Die Abschnitte 1a bis 1c sind verworfene Varianten.
Gültige Tweak-Werte: **Urteil = «Liste»**, **Prüfpunkte = «Gruppiert»**. Die anderen Tweak-Varianten nicht umsetzen.
Die Zahlen in der Referenz sind Beispieldaten und werden im Code aus dem Lauf berechnet.

## Fidelity

**High-fidelity.** Farben, Schriften, Abstände und Texte sind final. A4 hoch = 794 × 1123 CSS-px (96 dpi). Alle px-Werte unten beziehen sich darauf.

---

## Technischer Entscheid

| Punkt | Entscheid |
|---|---|
| Rendering | **HTML-Template (Jinja2) → PDF mit WeasyPrint.** Matplotlib reicht nicht für Tabellen mit Seitenumbruch und wiederholtem Tabellenkopf. |
| Neue Abhängigkeiten | `jinja2>=3.1`, `weasyprint>=62` in `requirements.txt` (Abschnitt «PDF-Report»). |
| Windows | WeasyPrint braucht Pango. Installation über MSYS2 (`pacman -S mingw-w64-x86_64-pango`) oder das WeasyPrint-Windows-Paket. In `README.md` des Repos dokumentieren. |
| Fallback | Fehlt WeasyPrint (ImportError/OSError), wirft `report_pdf` eine verständliche Meldung: «PDF-Report braucht WeasyPrint – siehe README». Keinen stillen Rückfall auf das alte Layout. |
| Modellbild | PNG aus `Result.print_parts` mit **Matplotlib mplot3d** (keine neue Abhängigkeit), eingebettet als `data:image/png;base64`. |
| Schriften | Instrument Sans (400/500/600/700) und IBM Plex Mono (400/500/600) als TTF unter `assets/fonts/` (OFL-Lizenz, von Google Fonts), eingebunden per `@font-face` mit `file://`-URL. |
| Matplotlib | Bleibt für das Modellbild. Die alten Diagrammfunktionen `_cover_page`, `_bar_chart` und `_histogram_thicknesses` entfernen. |

## Neue und geänderte Dateien

```
core/output/report.py            ÄNDERN   report_pdf(data) → bytes via WeasyPrint; elements_csv bleibt unverändert
core/output/report_data.py       NEU      ReportData + build_report_data(...): alle Werte fertig formatiert, UI-frei
core/output/report_image.py      NEU      model_png(parts, marks, storey_colors) → bytes
core/output/templates/report.html.j2   NEU
core/output/templates/report.css       NEU
assets/fonts/*.ttf               NEU
core/output/result.py            ÄNDERN   zusätzliche Felder (siehe unten), report_pdf(df, context)
core/generation.py               ÄNDERN   Felder befüllen
ui/sheet_check.py, ui/state.py, ui/state_views.py   ÄNDERN   neue Signatur, Prüfbericht ohne Ergebnis
tests/test_report.py             ÄNDERN   + tests/test_report_data.py NEU
```

---

## Schritt 1: Daten im `Result` ergänzen

`Result` (`core/output/result.py`) enthält heute für den Report zu wenig: Die Prüfpunkte sind nur als Sätze vorhanden, und Überhänge sowie Steckverbinder fehlen ganz. Diese Felder ergänzen (alle mit Defaultwert, damit Tests und Skripte weiterlaufen):

```python
check_points: list[dict] = field(default_factory=list)       # core.analysis.check_points.check_points(ifc, df)
overhangs: list[Overhang] = field(default_factory=list, repr=False)   # core.parts.overhangs.overhangs(...)
connector_count: int = 0                                     # len(plan)
joint_count: int = 0                                         # len({(v.bottom, v.top) for v in plan})
pegs_per_part: dict[str, int] = field(default_factory=dict)  # Zapfen je Teil (Teil = mesh_names[v.bottom])
clearance_mm: float = 0.0
settings: dict = field(default_factory=dict)                 # scale, pitch_mm, angle, windows, doors, profile, material
```

In `core/generation.py`:
- `generate()` legt `supports` (Rückgabe von `overhangs(...)`) als `overhangs` in das `Result`.
- `_connect_parts()` gibt zusätzlich `plan` und `clearance` zurück. Daraus `connector_count`, `joint_count` und `pegs_per_part` berechnen. Gibt es keine Verbinder: 0 und `{}`.
- `check_points=check_points(ifc, df)` setzen (Import aus `core.analysis.check_points`).
- `settings` aus `run` füllen: `scale`, `pitch_mm`, `angle`, `windows`, `doors`, `profile` (ganzes Dict), `material` (ganzes Dict).

## Schritt 2: `core/output/report_data.py`

Reine Funktionen ohne UI- und ohne WeasyPrint-Import. Sie liefern fertig formatierte Strings, damit das Template keine Logik enthält.

```python
@dataclass
class ReportData:
    head: dict            # projekt, datei, schema, datum, massstab, regelset, total, printed, parts_n
    specs: list[dict]     # Seitenleiste Seite 1: {key, value, icon, icon_data}
    image_png: bytes | None
    verdict: list[dict] | None    # None = Prüfbericht ohne Ergebnis
    parts: list[dict]             # Drucktteile-Tabelle
    decisions: list[dict]         # Regelwerk-Balken
    classes: list[dict]           # Druckbarkeit je IFC-Klasse
    check_groups: list[dict]      # Prüfpunkte gruppiert
    check_summary: str            # «6 PUNKTE · 2 MIT HANDLUNGSBEDARF»
    elements: list[dict]          # Anhang

def build_report_data(df, ifc_meta: dict, result: Result | None, scale: int, profile: dict,
                      material: dict, check_points: list[dict], ruleset_name: str) -> ReportData
```

`ifc_meta` = `{"projekt": IfcProject.Name oder Dateistamm, "datei": filename, "schema": ifc.schema, "real_m": [x,y,z]}`. `real_m` kommt aus `model_overview(...)["dimensions_m"]`.

### 2.1 Kopf (`head`)
| Feld | Quelle | Format |
|---|---|---|
| projekt | `IfcProject.Name`, sonst `Path(filename).stem` | Text |
| datei | Dateiname | Text |
| schema | `ifc.schema` | «IFC4» |
| datum | `datetime.now()` | `25.10.2026 13:42` |
| massstab / regelset | `f"1:{scale}"` / `ruleset_name` | «1:200» |
| total | `len(df)` | `1206` (ohne Tausendertrenner bis 9999, ab 10 000 `10'000`) |
| printed | `df["is_printed"].sum()` | |
| parts_n | `len(result.parts)` | |

### 2.2 Seitenleiste Seite 1 (`specs`), in dieser Reihenfolge
| Key (Versalien) | Wert | Icon |
|---|---|---|
| SCHEMA | `IFC4` | – |
| MASSSTAB | `1:200` | Massstabsbalken |
| DRUCKER | `{profile.name}` + Zeilenumbruch + `Düse {nozzle_mm:.1f} mm` | Düse mit `{nozzle_mm:.2f} mm` |
| MATERIAL | `material.name` | – |
| VOXEL-PITCH | `{pitch_mm:.2f} mm` | Würfelreihe mit `{pitch_mm:.1f} mm` |
| AUSRICHTUNG | `{angle:.1f}°` | Winkel, gedreht um `angle` |
| FENSTER · TÜREN | Modus Fenster; weicht der Modus der Türen ab: `{windows} · {doors}` | Wandstück: Fenster nach Fenstermodus, Tür nach Türmodus |
| MODELL REAL | `{x:.1f} × {y:.1f} × {z:.1f} m` (eine Zeile, `white-space:nowrap`) | – |
| STECKVERBINDER | `{connector_count} an {joint_count} Fugen`; ohne Verbinder: `keine` | Zapfen und Tasche im Schnitt |
| ÖFFNUNGEN | `{metrics["Öffnungen"]} eingesetzt` | – |

### 2.3 Urteil (`verdict`), Darstellung «Liste», 4 Zeilen
| Titel | Wert | Untertitel | Stufe |
|---|---|---|---|
| Druckbar | Anzahl gedruckter Bauteile | `alle gedruckten Bauteile ≥ {min_wall_mm} mm, {Verdickt} dafür verdickt` | ok, wenn kein gedrucktes Bauteil `status == "nicht_druckbar"` und `action == "behalten"` hat. Sonst warn mit Untertitel `{n} Bauteile unter {min_wall} mm ohne Massnahme` |
| Wasserdicht | `{k} / {n}` (k = Teile mit `export_watertight`) | `alle Teile auch nach dem STL-Export geschlossen` bzw. `nicht dicht: {Namen}` | ok, wenn k == n, sonst err |
| Passt aufs Druckbett | `{x:.0f}×{y:.0f}×{z:.0f}` (Modell-mm, aus `model_overview` `model_mm`) | `mm, Bauraum {bx:.0f} × {by:.0f} × {bz:.0f} mm` | ok bei `fits`, sonst err mit Untertitel `Massstab 1:{recommendation} würde passen` |
| Stützen nötig / Keine Stützen | `{Σ support_mm2 / 100:.1f} cm²` bzw. `–` | Bauteile an der grössten Stelle je relevantem Teil, kommagetrennt (wie `_overhang_notes`) | warn, wenn ein Overhang `relevant` ist, sonst ok |

Marke: ok = `✓`, warn und err = `!`.

### 2.4 Druckteile (`parts`), eine Zeile je Teil in `result.print_parts`
| Spalte | Quelle | Format |
|---|---|---|
| TEIL | Teilname, Farbquadrat `preview.storey_color(rank)` in Geschossreihenfolge | `UG` |
| GRÖSSE (MM) | `mesh.extents` | `186 × 142 × 18` |
| STÜTZFLÄCHE | `support_mm2` des passenden Overhang, nur wenn `relevant` | `1.3 cm²`, sonst `–` in #8A8E95 |
| ZAPFEN | `pegs_per_part[name]` | `6 Zapfen`, sonst `–` |

### 2.5 Regelwerk (`decisions`), 6 Segmente, immer in dieser Reihenfolge
| Label | Zählung | Farbe |
|---|---|---|
| behalten | `action == "behalten"` und Regel vorhanden | #17191C |
| verdicken | `action == "verdicken"` | #FF6B2C |
| füllen | `action == "fuellen"` | #F2A93B |
| als Band | `action == "band"` | #2CC6C6 |
| entfernen | `action == "entfernen"` und `rule != ""` | #7B8594 |
| ohne Regel | `rule == ""` | #D03B40 |

Die Summe muss `len(df)` ergeben. Dafür einen Test schreiben. Segmentbreite = Anteil in %. Segmente mit 0 werden im Balken weggelassen, in der Legende aber angezeigt.

### 2.6 Druckbarkeit je IFC-Klasse (`classes`)
Gruppiert nach `ifc_class`, je Zeile: `n`, `ok`, `kr`, `ni` (Status der **gedruckten** Bauteile der Klasse), `sk` (nicht gedruckt). Die Breiten sind `x/n·100 %`.
Aktion: die vorkommenden Aktionen in der Reihenfolge behalten, verdicken, füllen, als Band, entfernen, verbunden mit ` · `. Klassen ohne Regel heissen `keine Regel`.
Farbe der Aktion: behalten #17191C, verdicken und als Band #C94A12, füllen #B4690E, entfernen #7B8594, keine Regel #D03B40.
Sortierung: zuerst Klassen mit gedruckten Bauteilen (absteigend nach n), dann die übrigen (absteigend nach n).
**Höchstens 13 Zeilen.** Bei mehr Klassen folgt eine Schlusszeile `+ {k} weitere Klassen ({Σn} Bauteile) – siehe Anhang`.

### 2.7 Prüfpunkte (`check_groups`), Darstellung «Gruppiert»
Quelle: `check_points(ifc, df)`, **ohne** `georeferenz` (wie in `checklist`), dazu zwei Punkte aus dem Lauf: «Öffnungen ohne Fenster oder Tür ausgeschnitten» und «Decken mit Gefälle eben gemacht». Beide stehen heute als Sätze in `_element_notes`. Sie sollen künftig strukturiert als Punkte mit `kind = "oeffnungen"` bzw. `"gefaelle"` kommen.

Stufe je `kind` (gleich wie `ui/sheet_check.SEVERITY`):
| Stufe | kinds | Gruppentitel | Akzent | Textfarbe |
|---|---|---|---|---|
| err | keine, geometry | Handlungsbedarf | #D03B40 | #B02E33 |
| warn | geerbt, ausreisser, umgebung | Prüfen | #B4690E | #8F5208 |
| info | alle übrigen | Zur Kenntnis | #7B8594 | #4F5662 |

Je Punkt: `t` = title, `e` = Einträge als `Text (n)`, verbunden mit ` · ` (ohne Einträge: `explanation`), `n` = Summe der Anzahlen bzw. `–`, `fix` = Text «Was tun».
Neu in `check_points.py` eine Tabelle `_FIX` je kind ergänzen:
```
keine       → «Regeln im Blatt 03 ergänzen»
geometry    → «IFC-Geometrie im Autorenwerkzeug prüfen»
geerbt      → «Keine Aktion; Regel bei Bedarf eigens setzen»
aggregate   → «Keine Aktion»
storeys     → «Keine Aktion»
ausreisser  → «Im Blatt 03 je Bauteil übersteuern»
umgebung    → «Im Blatt 03 je Bauteil übersteuern»
versatz     → «Keine Aktion; Lage bleibt im IFC»
oeffnungen  → «Keine Aktion»
gefaelle    → «Keine Aktion»
```
`check_summary` = `{n} PUNKTE · {m} MIT HANDLUNGSBEDARF` (m = Anzahl err). Ohne err: `{n} PUNKTE`. Ohne Punkte: Block «✓ Keine Auffälligkeiten.» auf #EEF8F5 mit Text #0E8F7E.

### 2.8 Anhang (`elements`): alle Zeilen von `df`
Sortierung: Geschoss nach `storey_order`, dann `ifc_class`, dann `name`.
| Spalte | Quelle | Format |
|---|---|---|
| KLASSE | ifc_class | |
| NAME | name | eine Zeile, mit `…` gekürzt |
| GESCH. | storey | |
| REAL (MM) | massgebende Dicke real: `package_thickness_mm`, sonst `layer_thickness_mm`, sonst `thickness_min_mm` | `365` (0 Nachkommastellen), NaN → `–` |
| MODELL (MM) | `thickness_model_mm` | `1.83`, NaN → `–` |
| AKTION | action, angezeigt als füllen / als Band / keine Regel (wie 2.6) | Farbe wie 2.6 |

Keine Statuspunkte in dieser Tabelle.

## Schritt 3: `core/output/report_image.py`

`model_png(parts: dict[str, Trimesh], marks: dict[str, Trimesh], colors: dict[str, str]) -> bytes`
- Netze mit `core.voxels.meshing.decimated` gemeinsam auf **höchstens 40 000 Dreiecke** reduzieren.
- Matplotlib `Axes3D`, `Poly3DCollection` je Teil in seiner Geschossfarbe, Flächen schattiert: Helligkeit = 0.55 + 0.45·max(0, n·l) mit l = normalisiert (−1, −1, 2). Die Stützstellen (`marks`) kommen dazu in #D61A3C.
- Isometrische Ansicht `view_init(elev=30, azim=-60)`, `set_box_aspect` nach den Ausdehnungen, Achsen aus, Hintergrund #F6F4F0.
- Grösse 1000 × 680 px (`figsize=(10, 6.8)`, `dpi=100`), PNG ohne Rand (`bbox_inches="tight", pad_inches=0.1`).
- Ohne Teile (Prüfbericht) gibt die Funktion `None` zurück. Das Template zeigt dann die gestreifte Fläche mit dem Text «Noch nicht erzeugt – Modellansicht folgt nach «STL erzeugen»».

## Schritt 4: Template und CSS

`report.html.j2` mit drei Abschnitten. Die Seitenumbrüche macht WeasyPrint selbst. Den Anhang als echtes `<table>` mit `<thead style="display:table-header-group">` setzen, so wiederholt sich der Kopf auf jeder Folgeseite.

### Seitenaufbau (`report.css`)
```css
@page { size: A4; margin: 0; }
@page :not(:first) { margin: 64px 0 40px; @top-center { content: element(band); width: 100%; } 
                     @bottom-right { content: counter(page) " / " counter(pages); font: 500 8.25pt "IBM Plex Mono"; color: #8A8E95; margin-right: 30pt; } }
.band { position: running(band); }
```
Hinweis: Das obere dunkle Band steht in der Referenz innerhalb der Seite. In WeasyPrint wird es über `position: running()` auf Seite 2 und alle Folgeseiten wiederholt. Statt «2 / 3» gilt dort `counter(page) / counter(pages)`, weil der Anhang mehrere Seiten haben kann.

### Seite 1: Übergabe (`display:grid; grid-template-columns:236px 1fr; height:1123px`)
- **Seitenleiste** (#17191C, Text #EDECE8, `padding:40px 26px`, Spalte mit `gap:26px`):
  - Logo `assets/logo.svg` (30 px, Füllung #EDECE8, Dach #E8562A/#903216) + «IFC2Print» Instrument Sans 700 17px.
  - «PROJEKT» Plex Mono 600 10px, `letter-spacing:.08em`, #FF6B2C. Projektname Instrument Sans 600 18px/1.2. Dateiname Plex Mono 400 11px/1.4 #A0A6B0, `word-break:break-all`.
  - Kenndaten-Zeilen: `padding:8px 0`, `border-top:1px solid #2E333C`, `display:flex; justify-content:space-between; align-items:center`. Key Plex Mono 500 9.5px, `letter-spacing:.08em`, #8A8E95. Wert Plex Mono 500 12.5px/1.25.
  - Ganz unten: `Erzeugt {datum}` und `Seite 1 / {pages}`, Plex Mono 400 11px/1.4 #8A8E95.
- **Hauptspalte** (`padding:40px 36px`, Spalte mit `gap:20px`):
  - Kicker «01 · ÜBERGABE» Plex Mono 600 11px, `letter-spacing:.1em`, #C94A12.
  - Titel «Druckmodell 1:200, 5 Teile» Instrument Sans 600 30px/1.1, `letter-spacing:-.025em`.
  - Modellbild 340px hoch, `border-radius:14px`, `object-fit:contain`, Hintergrund #F6F4F0.
  - Urteil «Liste»: `border-top:1.5px solid #17191C`. Je Zeile Grid `26px 1fr auto`, `gap:12px`, `padding:9px 0`, `border-bottom:1px solid #ECE8E0`. Marke als Kreis 22px, Hintergrund ok `rgba(14,143,126,.10)` / warn `rgba(180,105,14,.12)` / err `rgba(208,59,64,.10)`, Zeichen Plex Mono 700 12px in #0E8F7E / #B4690E / #D03B40. Titel Instrument Sans 600 13.5px. Untertitel 400 11.5px/1.3 #5E6269. Wert Plex Mono 600 15px.
  - Druckteile: Kopf-Grid `70px 1fr 80px 70px`, `gap:8px`, Plex Mono 600 9.5px, `letter-spacing:.06em`, #8A8E95, mit den Titeln «TEIL · GRÖSSE (MM) · STÜTZFLÄCHE · ZAPFEN». Zeilen Plex Mono 400 12px, `padding:7px 0`, `border-top:1px solid #ECE8E0`. Teilname 600 mit Farbquadrat 9px (`border-radius:2px`). Stützfläche in #B4690E, wenn vorhanden.

### Seite 2: Regelwerk (Ränder 40 px seitlich)
- Kicker «02 · REGELWERK 1:200», Titel «1206 Bauteile im IFC, 934 gedruckt» Instrument Sans 600 24px/1.1.
- Verteilungsbalken: 14px hoch, Segmente nebeneinander, `border-right:1.5px solid #fff`. Darunter ein Grid mit 6 Spalten, `gap:8px`: Zahl Plex Mono 600 16px, Label Instrument Sans 500 11px #5E6269 mit Farbquadrat 8px.
- Druckbarkeit je Klasse:
  - Kopfzeile links «DRUCKBARKEIT JE IFC-KLASSE» (Plex Mono 600 10px #8A8E95), rechts die Legende mit Quadraten 9px und grauem Text: DRUCKBAR, KRITISCH, NICHT DRUCKBAR, NICHT GEDRUCKT.
  - Zeilen-Grid `180px 1fr 44px 130px`, `gap:12px`, `padding:5px 0`, `border-top:1px solid #ECE8E0`. Klasse Plex Mono 500 12px. Balken 16px hoch, `border-radius:4px`, Hintergrund #F6F4F0, Segmente in **Pastell**: druckbar #93D8C4, kritisch #FFC9A3, nicht druckbar #F4A6B4, nicht gedruckt #D6D9DE. Anzahl Plex Mono 600 12px rechtsbündig. Aktion Plex Mono 500 11.5px in Aktionsfarbe.
- Prüfpunkte «Gruppiert»:
  - Kopfzeile links «PRÜFPUNKTE», rechts `check_summary`.
  - Je Gruppe ein Block mit `border-radius:10px`, Hintergrund = Akzent 7 % auf Weiss. Kopf `padding:8px 12px` auf Akzent 14 % auf Weiss, Titel Instrument Sans 600 12px und Anzahl Plex Mono 600 11px in der Textfarbe der Stufe.
  - Punkte im Grid `1fr 150px 44px`, `padding:8px 12px`, `border-top:1px solid rgba(23,25,28,.06)`. Titel Instrument Sans 600 12.5px, Einträge Plex Mono 400 11px/1.35 #5E6269. «Was tun» Instrument Sans 400 11.5px #5E6269. Anzahl Plex Mono 600 12.5px rechtsbündig.
  - Für WeasyPrint die Mischfarben vorberechnen, z. B. err 7 % = #FDF3F3, 14 % = #FAE7E8. Nicht auf `color-mix()` verlassen.

### Seite 3 ff.: Anhang
- Kicker «03 · ANHANG», Titel «Bauteiltabelle».
- Tabellenkopf: Hintergrund #F6F4F0, `border-radius:6px`, Plex Mono 500 9.5px, `letter-spacing:.05em`, #8A8E95. Spalten 150px / 1fr / 48px / 56px (rechtsbündig) / 70px / 80px, `padding:8px 10px`.
- Zeilen: `padding:6px 10px`, `border-bottom:1px solid #ECE8E0`, Plex Mono 400 11px/1.2. Name in Instrument Sans 12px. `tr { break-inside: avoid; }`.

### Icons (Inline-SVG im Template, Farben auf dunklem Grund)
Die genauen Pfade stehen in der Referenzdatei unter 2a, Seite 1, und können 1:1 übernommen werden. Parameter:
- **Massstab:** Balken 48 × 5 px, 4 Felder abwechselnd #EDECE8 und leer, Rahmen 1px #EDECE8, ohne Zahlen.
- **Düse:** viewBox 44×44: Körper #5E6269, Mutter #A0A6B0, Kegel #EDECE8, Austritt #FF6B2C, darunter Text `{nozzle:.2f} mm` Plex Mono 600 7px #FF6B2C.
- **Voxel:** viewBox 74×36: drei Würfel in Schrägansicht (Front #EDECE8, Deckel #A0A6B0, Seite #5E6269), Deckkraft 1 / 0.3 / 0.12, links eine Masslinie #FF6B2C mit Text `{pitch:.1f} mm`, um −90° gedreht.
- **Winkel:** viewBox `0 -2 40 44`: gestrichelte Achsen #5E6269, Grundriss-Rechteck (Strich #EDECE8) und Arm #FF6B2C in einer Gruppe mit `transform="rotate({-angle} 4 20)"`. Bleibt bis ±45° innerhalb der Box.
- **Fenster · Türen:** viewBox 52×34: Wandstück schräg. Je Modus: `vertieft` = Laibung links und unten #5E6269, Rückfläche #B8BCC2; `geschlossen` = bündig mit Kontur #8A8E95; `ausgeschnitten` = Öffnung #17191C. Fenster und Tür einzeln nach ihrem Modus.
- **Steckverbinder:** viewBox 48×32: oben das Teil mit Tasche (#EDECE8), unten das Teil (#5E6269) mit Zapfen als Trapez #FF6B2C (Flanke 15° wie `PEG_TAPER_DEG`).

## Schritt 5: Aufrufe anpassen

- `Result.report_pdf(df, context: dict)`. `context` = `{"filename", "ifc_meta", "profile", "material", "ruleset_name", "scale"}` aus der Sitzung (`ui/state.py`).
- `ui/sheet_check.py`: Knopf «PDF-Report» übergibt `context`.
- `ui/state_views.check_report_pdf`: ruft denselben Report mit `result=None` auf. Dann gilt:
  - Seite 1 ohne Urteil und ohne Druckteile, dafür der Hinweis «Noch nicht erzeugt».
  - Seiten 2 und 3 wie gehabt.
  - Dateiname bleibt `_pruefbericht.pdf`.

## Schritt 6: Tests

- `tests/test_report.py` bleibt grün. Magic Bytes `%PDF`, leere Tabelle und fehlende Dicken mit dem neuen Aufruf.
- `tests/test_report_data.py` (neu, ohne WeasyPrint):
  - Summe der `decisions` = `len(df)`.
  - Klassen höchstens 13 Zeilen plus Schlusszeile.
  - Stufen-Zuordnung der kinds.
  - Formatierung: Datum, `1:200`, `–` bei NaN.
  - `verdict is None` ohne Ergebnis.
  - Winkel-Text `-12.5°`.
- WeasyPrint-Tests mit `pytest.importorskip("weasyprint")` absichern.
- Mit `scripts/generate_stl.py` am NEST-Modell einen Report erzeugen, öffnen und mit der Referenz 2a vergleichen.

## Design-Tokens

| Token | Hex |
|---|---|
| Text | #17191C |
| Muted | #5E6269 |
| Faint | #8A8E95 |
| Linie | #ECE8E0 (fein), #DDD8CE |
| Fläche | #F6F4F0 |
| Seitenleiste | #17191C, Linie #2E333C, Text #EDECE8 / #A0A6B0 |
| Primär (PETG) | #FF6B2C, Text-Akzent #C94A12 |
| ok / warn / err / skip | #0E8F7E / #B4690E / #D03B40 / #7B8594 |
| Pastell-Status | druckbar #93D8C4, kritisch #FFC9A3, nicht druckbar #F4A6B4, nicht gedruckt #D6D9DE |
| Geschossfarben | `core.output.preview.STOREY_COLORS` |

Schriften: Instrument Sans (Text, Titel), IBM Plex Mono (Zahlen, Labels, Tabellen). Gleich wie `ui/theme.css`.

## Dateien in diesem Paket

- `PDF Report.dc.html`: Design-Referenz, Abschnitt **2a** (Tweaks: Urteil «Liste», Prüfpunkte «Gruppiert»).
- `support.js`: wird zum Öffnen der Referenz im Browser gebraucht.

## Reihenfolge für Claude Code (je Schritt testen, dann committen)

1. `Result` und `generate` ergänzen, bestehende Tests laufen.
2. `report_data.py` und dessen Tests.
3. `report_image.py`, das PNG einmal manuell prüfen.
4. Template, CSS und Schriften, `report_pdf` auf WeasyPrint umstellen.
5. UI-Aufrufe und Prüfbericht anpassen.
6. Requirements und README (Windows-Installation von WeasyPrint), alte Matplotlib-Diagramme entfernen.
