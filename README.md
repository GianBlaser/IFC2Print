# IFC2Print – Massstabsmodell-Generator

Prüft ein IFC-Modell für einen Massstab und ein Druckerprofil auf Druckbarkeit, bereinigt es regelbasiert und erzeugt druckfertige, wasserdichte STL-Dateien – auf Wunsch geschossweise und mit Steckverbindern.

| | |
|---|---|
| Modul | Digital Twin Programmieren (TA.BA_DT_PROGR), HSLU Digital Construction, HS26 |
| Autor | Gian Blaser (Einzelarbeit) |
| Repository | https://github.com/GianBlaser/IFC2Print |

Referenzdrucker ist der Prusa MK4 mit 0.4-mm-Düse. Der Code ist Python, die Oberfläche ist mit NiceGUI gebaut, der 3D-Viewer läuft über `ui.scene`. Wo NiceGUI allein nicht reicht (Kanten und Aufbau-Animation im Viewer, zwei Tabellenzellen), stehen kleine JavaScript- bzw. Vue-Bausteine als Text in Python-Dateien (`ui/viewer_js.py`, `ui/texts.py`); eigene `.js`-Dateien gibt es nicht.

Bezeichner (Variablen, Funktionen, Dateien, Tabellenspalten) sind englisch, Kommentare, Docstrings und die Oberfläche deutsch.

---

## Was das Programm tut

1. **Upload:** Beim Öffnen erscheint ein Beispielmodell (`config.START_MODEL`, voll nutzbar). Eine eigene IFC-Datei wird in der Oberfläche hochgeladen und einmalig trianguliert. Im Setup werden Massstab, Druckerprofil, Material, Geschosse, Qualität, Fenster und Türen, die automatische Ausrichtung und die Steckverbinder gewählt.
2. **Analyse/Status:** Jedes Bauteil erhält im gewählten Massstab einen Druckbarkeitsstatus (druckbar, kritisch, nicht druckbar), der in der Bauteiltabelle und im 3D-Viewer sichtbar ist. Das Panel «Geschosse · Modell» rechts zeigt die Matrix Geschoss × Status, die Druckbett-Auslastung je Achse (mit Massstab-Vorschlag, wenn es knapp wird) und einen Geometrie-Check (ok / fehlt / defekt).
3. **Regeln:** Ein Regelwerk je Massstab legt je IFC-Klasse fest, ob ein Bauteil behalten, verdickt, durch einen Füllquader ersetzt, als Band (Geländer) gedruckt oder entfernt wird. Plattenartige Bauteile (Wände, Decken, Dächer, Bekleidungen) werden zu Paketen zusammengefasst und paketweise auf ganze Voxel skaliert. Bauteile der Umgebung (Stützmauern, Terrain) werden erkannt und nicht gedruckt; jedes Bauteil lässt sich einzeln übersteuern.
4. **Erzeugen:** Die druckbaren Bauteile werden in ein gemeinsames Voxelgitter gelegt, Fenster und Türen wirken auf dieses Gitter, Öffnungen ohne Fenster oder Tür (Treppenaugen, Schächte) werden ausgeschnitten. Danach wird das Gitter in Geschoss- und Dachteile aufgeteilt, zu wasserdichten Teilen vernetzt, optional mit Steckverbindern versehen und mit Filament-, Kosten- und Zeitschätzung ergänzt. Pro Sitzung läuft nur eine Erzeugung gleichzeitig; das Gebäude baut sich im Viewer synchron zum Fortschritt von unten nach oben auf.
5. **Downloads:** STL komplett, ZIP mit einer STL je Teil (Geschoss bzw. Dach), Druckplatte (alle Teile auf dem Druckbett verteilt), PDF-Report, Prüfbericht (PDF) und CSV der Bauteiltabelle.

### Bedienung

```
┌──────┬──────────────────────────────────────────────┬───┬──┐
│ LOGO │  Kapitel-Blatt (01–05)          3D-Viewer    │ ◂ │IFC│
│  01  │  03: Tabs «IFC-Klassen» | «Bauteile»         │   │STA│
│  02  │      Breite per Griff ziehbar ⇔              │ ▌ │STL│
│  03  │                                     [Panel   │   │ ⇕ │
│  04  │                                     Geschosse│   └──┘
│ ──── │                                     · Modell]│
│  05● │                                              │
│  ↺   ├──────────────────────────────────────────────┴──────┤
│      │ AUSGABEZIEL [FDM] [Resin bald] [Lasercut bald] …     │
│      │ Filament ⓘ | Druckzeit ⓘ | Kosten ⓘ | Downloads      │
└──────┴──────────────────────────────────────────────────────┘
```

- **Leiste links:** 01 Datei · 02 Setup · 03 Regeln · 04 Ausgabe, unter dem Trennstrich 05 Prüfen (Zähler = Anzahl Prüfpunkte), unten ↺ Verlauf. Erledigte Kapitel tragen ein ✓.
- **03 Regeln:** Oben das Regelset (= Massstab, synchron mit 02). Tab «IFC-Klassen» setzt die Regel je Klasse, Tab «Bauteile» ist die Bauteiltabelle mit Filter, Sammelaktionen und Detail. Die Breite des Blatts lässt sich am rechten Rand ziehen.
- **04 Ausgabe:** Erzeugen mit Fortschritt; danach schliesst das Blatt, die Ansicht springt auf STL.
- **05 Prüfen:** Prüfpunkte als Karten je Kategorie (Klassen ohne Regel, defekte Geometrie, doppelte Geschosse, Ausreisser, Umgebung, Georeferenz) mit Sprung zum Beheben und Downloads (Prüfbericht, CSV, Report).
- **Ansicht rechts:** senkrechte Leiste IFC · STAT · STL · ⇕ (auseinander). Der dunkle Balken klappt das Panel «Geschosse · Modell» auf: Ein Klick auf eine Matrix-Zelle, -Zeile oder -Spalte öffnet 03 › Bauteile mit diesem Filter und zeigt im Viewer nur diese Bauteile («alle Bauteile zeigen» blendet wieder alles ein; aus der STL-Ansicht wechselt der Viewer dafür auf STAT), das Farbquadrat blendet das Geschoss aus, Hover hebt das Geschoss im Viewer hervor.
- **Untere Leiste:** Ausgabeziele (nur FDM umgesetzt, die übrigen als «bald» angelegt, `config.OUTPUT_TARGETS`), Kennzahlen mit Herleitung beim Darüberfahren und die Downloads. Nach einer Änderung gilt das Ergebnis als **veraltet**: Es bleibt sichtbar, die Downloads sind gesperrt, bis neu erzeugt ist.
- Offenes Kapitel, Tab in 03, Breite von 03, Panel offen/zu und ausgeblendete Geschosse bleiben nach dem Neuladen erhalten (`app.storage.user`).

---

## Schnellstart

Virtuelle Umgebung anlegen und Abhängigkeiten installieren:

| Plattform | Befehle |
|---|---|
| Windows | `python -m venv .venv`<br>`.venv\Scripts\activate`<br>`pip install -r requirements.txt` |
| macOS / Linux | `python3 -m venv .venv`<br>`source .venv/bin/activate`<br>`pip install -r requirements.txt` |

**PDF-Report (WeasyPrint):** WeasyPrint setzt den Report aus einem HTML-Template und braucht dafür die Textbibliothek Pango.
Unter macOS (`brew install pango`) und Linux (Paket `libpango-1.0-0`) genügt die Paketverwaltung. Unter Windows kommt Pango aus MSYS2:

1. MSYS2 installieren: `winget install MSYS2.MSYS2` (oder Installer von https://www.msys2.org), Zielordner `C:\msys64`.
2. In der Konsole «MSYS2 MINGW64»: `pacman -S mingw-w64-x86_64-pango`
3. Fertig: IFC2Print findet `C:\msys64\mingw64\bin` selbst (`PANGO_DLL_DIR` in `config.py`). Liegt MSYS2 anderswo, die
   Umgebungsvariable `WEASYPRINT_DLL_DIRECTORIES` auf den `mingw64\bin`-Ordner setzen.

Fehlt Pango, meldet der Download «PDF-Report braucht WeasyPrint – siehe README»; STL, ZIP und CSV funktionieren weiter.
Die Schriften des Reports (Instrument Sans, IBM Plex Mono, OFL-Lizenz) liegen in `assets/fonts/`.

Oberfläche starten:

```bash
python main.py
```

Danach im Browser http://127.0.0.1:8080 öffnen. Optionale Umgebungsvariablen: `IFC2PRINT_DB` (Pfad der Datenbank), `IFC2PRINT_HOST` (Adresse, Standard `127.0.0.1`), `IFC2PRINT_SECRET` (Schlüssel der Browser-Speicherung; ohne Angabe wird einer erzeugt und in `.nicegui/secret.txt` abgelegt).

Ohne Oberfläche (Kommandozeile, schreibt ZIP und PDF nach `output/`):

```bash
python scripts/generate_stl.py testdaten/MFH_eBKPH_Test.ifc --scale 1:200 --quality entwurf
```

Tests:

```bash
python -m pytest
```

---

## Architektur

```
main.py                        Start: ruft app.launch() auf
app.py                         Datenbank öffnen, Seite registrieren, NiceGUI starten
  │
  ▼
ui/  page.py koordiniert · ein Blatt je Datei (sheet_*.py) · panel · viewer · theme.css
  │
  ▼
ui/state.py (Sitzung) ───────────► db/  database.py · schema.sql · seed/   (SQLite)
  │
  ▼
core/pipeline.py               Fassade: einzige Schnittstelle der Oberfläche zur Verarbeitung
  │
  ▼
core/generation.py             Ablauf der Erzeugung
  │
  ▼
core/  ifc → analysis → packages → voxels → openings → parts → connectors → output
```

`core/` kennt die Oberfläche nicht (geprüft von `tests/test_architecture.py`, mit allen Unterordnern). Dasselbe gilt für `db/`. Deshalb läuft die Verarbeitung unverändert in der NiceGUI-App, im Kommandozeilenskript und in den Tests. Jeder Name wird dort importiert, wo er definiert ist; nur `core/pipeline.py` reicht Namen für Oberfläche, Skripte und Tests weiter.

---

## Module

Die Unterordner von `core/` folgen den Verarbeitungsschritten; jede `__init__.py` nennt Zweck, Eingabe und Ausgabe des Schritts. Jede Datei beginnt mit einem Docstring (Zweck, Eingabe, Ausgabe).

| Datei | Aufgabe |
|---|---|
| `main.py` | Startpunkt |
| `app.py` | Öffnet die Datenbank, registriert die Seite und startet NiceGUI auf Port 8080 |
| `config.py` | Fachkonstanten mit Begründung (Druckbarkeit, Voxel, Fugen, Dächer, Pakete, Öffnungen, Steckverbinder, Kalkulation) und die Ausgabeziele. Massstabsabhängige Werte stehen in `db/seed/massstaebe.csv` |
| **core/** | |
| `core/pipeline.py` | Fassade: `analyse()` (Regeln, Umgebung, Ausnahmen je Bauteil, Pakete, Druckbarkeit), `resolve_quality()`, `alignment_angle()`; reicht `generate`, `Result`, Prüfpunkte und Viewer-Daten weiter |
| `core/generation.py` | `generate()` in benannten Schritten: Bauteile vorbereiten, Gitter bauen, in Teile aufteilen, Steckverbinder, Schätzung, Kennzahlen |
| **core/ifc/** | IFC einlesen |
| `model.py` | `IfcModel`: Bauteiltabelle, Geometrie je GUID (einmal trianguliert), Platten, Gefälle, Füller, Öffnungen; Versatz bei Landeskoordinaten |
| `geometry.py` | Triangulieren mit dem ifcopenshell-Iterator |
| `assignment.py` | Klassenfamilie, Geschoss (räumlicher Container) und Layer eines Bauteils |
| `openings.py` | Fenster, Türen, Vorhangfassaden (Füller mit Wirt-Wand) und Öffnungen ohne Füller |
| `schema.py` | Klassenhierarchie des Schemas (Vererbungskette, alle Produktklassen) |
| `table.py` | Bauteiltabelle: eine Zeile je physischem Bauteil |
| `layers.py` | Gesamtdicke des Materialschichtpakets (`IfcMaterialLayerSet`) |
| **core/analysis/** | Bauteile analysieren |
| `ruleset.py` | Regelwerk je Massstab (`Ruleset`, `ScaleParameters`): Regelschlüssel → Aktion und Kategorie |
| `surroundings.py` | Umgebung und Ausreisser erkennen |
| `printability.py` | Druckbarkeitsstatus im Modellmassstab |
| `check_points.py` | Prüfpunkte für Blatt 05 und Prüfbericht |
| **core/packages/** | Wandpakete |
| `plates.py` | Plattenartige Bauteile erkennen (Dickenrichtung, Achsen einrasten), Gefälle erkennen |
| `grouping.py` | Anliegende parallele Platten zu Paketen gruppieren (Union-Find) |
| `thickness.py` | Paketdicke und freistehende Glieder |
| `scaling.py` | Paket entlang seiner Normale auf ganze Voxel skalieren |
| **core/voxels/** | Voxelgitter |
| `alignment.py` | Dominante Wandrichtung erkennen und Modell achsparallel drehen |
| `elements.py` | Bauteile vorbereiten: auswählen, Pakete skalieren, Aktion anwenden |
| `mesh_voxels.py` | Netz → Voxel (Oberfläche, Innenraum nach Windungszahl) |
| `element_voxels.py` | Voxel eines Bauteils: mindestens 1 Voxel dick, Rückfall bei offenem Netz, verdicken, Gefälle ebnen, Öffnungen aussparen |
| `shell.py` | Alle Bauteile in ein gemeinsames Gitter, Spalten schliessen, Speicherbremse |
| `grid.py` | Datenbehälter `VoxelGrid` (mit `place`, `count_inside`) und `BuildingElement` |
| `meshing.py` | Marching Cubes, Taubin-Glättung, Dezimierung, winzige Schalen entfernen |
| `band.py` | Aktion «band»: Geländer als dünne Scheibe ins Gitter |
| **core/openings/** | Fenster und Türen |
| `detection.py` | Wirtspaket finden, Öffnung im Achsensystem des Pakets beschreiben |
| `fillers.py` | Füller den Paketen zuordnen und ins Gitter setzen |
| `windows.py` | Modi geschlossen / vertieft / ausgeschnitten, Laibungen, Füllquader |
| **core/parts/** | Geschossteile |
| `partitioning.py` | Gitter in Geschoss- und Dachteile aufteilen (Label je Voxel), Teile vernetzen |
| `storey_joints.py` | Fugenhöhe finden, je Spalte glätten, schmale Einstülpungen der Unterseite füllen |
| `cleanup.py` | Inseln, Kleinteile, hängende Stücke und Splitter dem Nachbarteil geben |
| `roof.py` | Dachschale und Dachträger erkennen |
| `print_layout.py` | Teile auf ein oder mehrere Druckbetten verteilen |
| `overhangs.py` | Überhänge je Teil: Brücke oder Stützen, Stützen auf dem Bett oder im Modell, rote Markierung |
| **core/connectors/** | Steckverbinder |
| `planning.py` | Kontaktflächen zwischen Teilen finden, Verbinder je Fuge planen |
| `joint.py` | Drei Zapfen einer Fuge platzieren, Form (rund/rechteckig) und Grösse wählen |
| `geometry.py` | Zapfen und Taschen als Kegelstümpfe, per Boolean in die Teile |
| **core/output/** | Ergebnis und Anzeige |
| `result.py` | `Result`: Teile, Kennzahlen, Downloads; Dichtheit am exportierten STL prüfen |
| `report.py` | PDF-Report (Jinja2-Template `templates/report.html.j2` + `report.css`, gesetzt mit WeasyPrint) und CSV der Bauteiltabelle |
| `report_data.py` | Alle Werte des PDF-Reports fertig formatiert: Urteil, Druckteile, Regelwerk, Druckbarkeit je Klasse, Prüfpunkte, Anhang |
| `report_image.py` | Modellbild des PDF-Reports: Druckteile isometrisch in Geschossfarben (Matplotlib mplot3d) |
| `estimate.py` | Filament, Kosten, Druckzeit (Schätzung) mit Rechenweg |
| `preview.py` | GLB je Geschoss für den Viewer, reduzierte STL-Vorschau |
| `view_data.py` | Vorschauen je Ansicht, Kamerarahmen, Bauteil unter dem Mauszeiger |
| `model_info.py` | Kennzahlen des Modells (Abmessungen, Bauraum, Geschosse) |
| **db/** | |
| `db/database.py` (+ `schema.sql`, `seed/`) | SQLite für Regeln, Massstab-Parameter, Druckerprofile, Material und Exportverlauf. Schema und Seed-CSVs werden beim Start eingespielt; Datenbanken mit den früheren deutschen Tabellen- und Spaltennamen werden dabei automatisch umbenannt (Daten bleiben) |
| **ui/** | |
| `ui/page.py` | Seite: baut Leiste, Blätter, Panel und untere Leiste auf und koordiniert sie |
| `ui/state.py` | Sitzungszustand eines Browser-Tabs (Modell, Ausnahmen, Ergebnis, Lauf-Schutz), Bindeglied zu `core.pipeline` |
| `ui/settings.py`, `state_views.py`, `run_history.py` | Einstellungen der Sitzung samt Massstab-Defaults; Kennzahlen, Matrix und Prüfbericht für die Anzeige; Verlaufseintrag eines Erzeugungslaufs |
| `ui/sheet_file.py`, `sheet_setup.py`, `sheet_rules.py`, `sheet_elements.py`, `sheet_output.py`, `sheet_check.py`, `sheet_history.py` | Je ein Blatt: 01 Datei, 02 Setup, 03 Regeln, 03 Bauteile, 04 Ausgabe, 05 Prüfen, Verlauf |
| `ui/panel.py`, `matrix.py`, `model_info.py` | Panel rechts: Ansichtsleiste, Matrix Geschoss × Status, Modell-Info |
| `ui/detail.py`, `rail.py`, `bottom_bar.py` | Detailfeld eines Bauteils, Leiste links, untere Leiste |
| `ui/viewer.py` | 3D-Viewer (`ui.scene`) mit GLB je Geschoss, Geschoss-Fokus, Aufbau-Animation |
| `ui/viewer_js.py`, `viewer_bed.py`, `viewer_blobs.py` | JavaScript-Bausteine des Viewers (Licht, Kanten, Schnittebene); Druckbett im Viewer; GLB-Zwischenspeicher mit Route `/glb/{key}.glb` |
| `ui/texts.py`, `widgets.py` | Texte, Tabellenspalten und Vorlagen; kleine Bausteine (`button`, `tag`, `set_class` …) |
| `ui/start_model.py` | Beispielmodell beim Öffnen (einmal je Server geladen, von allen Tabs geteilt) |
| `ui/theme.css` | Aussehen (helles und dunkles Theme) |
| **scripts/** | |
| `scripts/generate_stl.py` | Kommandozeile: IFC analysieren, Geschoss-ZIP und PDF-Report erzeugen |
| `scripts/baseline_metrics.py` | Regressions-Netz: friert Qualitätsmetriken des STL-Outputs ein (`--save`) und vergleicht spätere Läufe (`--compare`, mit `--all` für alle Testmodelle) |
| `scripts/wall_thicknesses.py` | Misst im erzeugten Gitter die sichtbare Wanddicke je Wandtyp und zählt die Öffnungen |
| `scripts/diagnostics.py` | Schnelle Diagnose eines unbekannten IFC ohne Voxelisieren |

---

## Regeln

Jede IFC-Klasse erhält genau eine von fünf Aktionen:

| Aktion | Bedeutung |
|---|---|
| `behalten` | Das Bauteil wird gedruckt, wie es im IFC ist. |
| `verdicken` | Einzelbauteile (Stützen, Träger) werden bei Bedarf allseitig auf die Mindestwand aufgedickt. |
| `fuellen` | Statt der Geometrie wird ein Füllquader aus der Bounding Box gedruckt (Verglasung). Der Quader liegt mittig, seine dünnste Achse ist mindestens die Mindestwand. |
| `band` | Geländer: eine dünne Scheibe vom Boden bis zur Geländerhöhe (Dicke `min_thickness_railing_mm` des Massstabs). |
| `entfernen` | Das Bauteil wird nicht gedruckt. |

Wände, Decken, Dächer und Bekleidungen in Paketen werden unabhängig von «behalten» oder «verdicken» als Paket auf ganze Voxel und die Mindestdicke gebracht (siehe Hülle).

Ein Regelschlüssel ist die IFC-Klasse (`IfcCovering`) oder die Klasse mit PredefinedType im Format «Klasse.PREDEFINEDTYPE» (`IfcCovering.CLADDING`). Der spezifischere Schlüssel gewinnt.

- **Vererbung:** Gesucht wird über die Vererbungskette des Schemas (`core.ifc.schema.class_chain`). `IfcSlabStandardCase` hat keine eigene Regel und erbt die von `IfcSlab`; in IFC4X3 heisst die Oberklasse `IfcBuiltElement`. Erst wenn die ganze Kette keine Regel hat, wird das Bauteil entfernt.
- **Aggregate:** Teile eines Ganzen (Platten und Pfosten eines `IfcRoof`, Läufe einer `IfcStair`, `IfcBuildingElementPart` einer Wand) folgen der Regel ihres Ganzen, sofern es eine hat. Feiner steuert ein Schlüssel «Ganzes/Teil», z.B. `IfcRoof/IfcMember`.
- **Sichtbar statt still:** Das Regelblatt listet die Klassen des Modells ohne eigene Regel, mit der Regel, die stattdessen gilt («wie IfcSlab» bzw. «keine Regel»). Ein Klick legt die Regel an. Blatt 05 und der Prüfbericht nennen geerbte Regeln, Teile, die ihrem Ganzen folgen, und Klassen ohne Regel.

Es gibt ein Regelset je Massstab (1:500, 1:200, 1:100, 1:50). Regeln und Massstab-Parameter (Mindestdicke Wand und Geländer, Laibungstiefe, Restkern, Qualitäten, Steckverbinder erlaubt, Öffnungs-Defaults) liegen als Seed in `db/seed/regeln.csv` und `db/seed/massstaebe.csv` und werden in SQLite gespeichert; eigene Änderungen bleiben erhalten.

### Umgebung

Stützmauern, Terrainkanten u.ä. sind oft normale `IfcWall` und gehören nicht ins Modell. `core/analysis/surroundings.py` setzt solche Bauteile auf «entfernen» (Kategorie «Umgebung»), wenn

- eines der Stichworte aus `SURROUNDINGS_KEYWORDS` (`config.py`, z.B. «stützmauer», «stützwand», «gelände», «aussenanlage», «retaining», «topograph») am Wortanfang im Namen, im Typnamen oder im Layer steht (`IfcPresentationLayerAssignment`, z.B. ArchiCAD-Ebene «011 Stützwände»). Wörter aus `SURROUNDINGS_EXCEPTIONS` zählen nicht («Geländer» beginnt mit «Gelände»), oder
- die Klasse Gelände oder Tiefbau ist (`SURROUNDINGS_CLASSES`: `IfcGeographicElement`, `IfcCivilElement`), oder
- das Bauteil direkt im Grundstück (`IfcSite`) statt in einem Geschoss liegt und im Grundriss überwiegend ausserhalb des Gebäudes. Das gilt nur, wenn das Modell Geschosse nutzt. Ein Dach, das ein Autorentool ins Grundstück legt, bleibt so Gebäude.

**Ausreisser** (`surroundings.outlier`): Gedruckte Bauteile, die weiter als `OUTLIER_FACTOR` × Gebäudegrösse vom Gebäudekern entfernt liegen (z.B. ein verschobenes Bibliotheksobjekt), erhalten die Kategorie «Ausreisser» und werden nicht gedruckt. Sonst würde das Voxelgitter um Hunderte Meter länger.

Die Bauteiltabelle enthält dafür die Spalten `type_name`, `layer` und `on_site`. Im Detailfeld eines Bauteils steht «Nur dieses Bauteil: drucken / nicht drucken / wie Regel»; die Ausnahme übersteuert Regel und Umgebungserkennung (`Session.exceptions`, `pipeline.analyse(..., exceptions)`).

---

## Druckbarkeit

Die Grenzen gelten für die Dicke im Modellmassstab (reale Dicke geteilt durch Massstab):

| Status | Bedingung | Wert bei Standardprofil |
|---|---|---|
| nicht druckbar | Dicke < `MIN_WALL_MM` | < 0.8 mm |
| kritisch (druckbar, aber fragil) | `MIN_WALL_MM` ≤ Dicke < `MIN_WALL_MM` + `CRITICAL_SPAN_MM` | 0.8 mm bis < 1.2 mm |
| druckbar | Dicke ≥ `MIN_WALL_MM` + `CRITICAL_SPAN_MM` | ≥ 1.2 mm |

`MIN_WALL_MM` = 0.8 mm (mindestens 2 Extrusionslinien à 0.4 mm), `CRITICAL_SPAN_MM` = 0.4 mm. Die Mindestwand kommt im Betrieb aus dem Druckerprofil der Datenbank; `config.py` dient als Fallback.

Als Bewertungsdicke dient die Paketdicke (alle direkt anliegenden Schichten, Spalte `package_thickness_mm`), sonst das Materialschichtpaket (Summe der Schichten des `IfcMaterialLayerSet`), sonst die kleinste Kante der orientierten Bounding-Box. Ein Glied, das auf mehr als 10 % seiner Fläche allein steht (`PACKAGE_COVERED_RATIO`), wird nach seiner Eigendicke beurteilt.

---

## Hülle (Voxel-Verfahren)

- **Ausrichten:** Die Hauptrichtung der Wände im Grundriss wird aus den Flächennormalen bestimmt (flächengewichtet, modulo 90°). Das Modell wird vor dem Voxelisieren so gedreht, dass die meisten Wände parallel zu X/Y stehen. Schräge Wände werden so nicht zu Treppenstufen. Abschaltbar im Setup (`core/voxels/alignment.py`).
- **Massgenau voxelisieren:** Ein Voxel gehört zu einem Bauteil, wenn sein Mittelpunkt im Bauteil liegt (Windungszahl entlang senkrechter Strahlen). Das gibt keinen systematischen Aufschlag, auch überlappende Teilkörper werden richtig gezählt. Räume zwischen Bauteilen bleiben hohl, massive Blöcke werden voll.
- **Mindestens 1 Voxel:** Wo ein Bauteil dünner als ein Voxel ist, kommen seine Oberflächen-Voxel dazu, nichts verschwindet still. Für nicht geschlossene Bauteile gilt ein Rückfall: Oberflächen-Voxel plus Füllung dünner Hohlräume.
- **Bauteilpakete:** Plattenartige Bauteile (`IfcWall*`, `IfcSlab`, `IfcRoof`, `IfcCovering`, `IfcPlate`, `IfcBuildingElementPart`) erhalten eine Dickenrichtung (Wände aus der 2D-Box im Grundriss, übrige aus der orientierten Box). Parallele Platten, die sich berühren (Spalt < halbe Mindestwand im Modell, mindestens `PACKAGE_GAP_MIN_MM` real) und in der Fläche überlappen, bilden ein Paket (`core/packages/`). Die Paketdicke entscheidet über Druckbarkeit und Skalierung: Eine 2 cm Bekleidung vor einer 47 cm Aussenwand wird nicht einzeln aufgedickt.
- **Paketweise skalieren:** Ein Paket wird nur entlang seiner Normale skaliert (Länge und Höhe bleiben). Zieldicke = ganze Voxel, gerundet, mindestens `min_thickness_wall_mm` des Massstabs (1.2 mm bei 1:200) für Wände bzw. die Mindestwand des Profils für Decken und Dächer. Achsparallele Pakete werden so eingerastet, dass beide Flächen knapp innerhalb von Voxelgrenzen liegen: Jede Wand desselben Typs hat überall gleich viele Voxel.
- **Verdicken:** Stützen und Träger (alles, was kein Paket bildet) werden mit der Aktion «verdicken» morphologisch dilatiert, bis die Mindestwand erreicht ist.
- **Spalten schliessen:** Nach dem Vereinigen aller Bauteile werden Voxel gefüllt, die entlang einer Achse beidseitig belegt sind (1-Voxel-Schlitze vom Einrasten). Breitere Spalten, Ecken und Treppenstufen bleiben (`shell.close_gaps`).
- **Öffnungen ohne Fenster oder Tür:** Treppenaugen, Schächte und Durchgänge (`IfcOpeningElement` ohne Füller) werden aus dem eigenen Bauteil ausgespart, im Paket mit derselben Skalierung wie das Bauteil. Das Ergebnis meldet ihre Anzahl.
- **Fenster und Türen:** Fenster, Türen und Vorhangfassaden (`IfcModel.filler`; Wirt-Wand über `IfcRelFillsElement` → `IfcRelVoidsElement`, sonst geometrische Suche) wirken auf das gemeinsame Gitter, über die ganze Paketdicke aller Schichten (`core/openings/`).
  - Modi: *geschlossen*, *vertieft* oder *ausgeschnitten*; Standard je Massstab aus `massstaebe.csv`.
  - *Geschlossen* setzt einen Füllkörper ein: Die Wand ist auch dann voll, wenn die Öffnung schon in der Wandgeometrie steckt.
  - *Vertieft* füllt zuerst und räumt dann innen und aussen eine Laibung aus (`reveal_depth_mm` des Massstabs, mindestens 1 Voxel). Der Restkern muss mindestens `min_core_reveal_mm` = 0.4 mm (eine Druckbahn) bleiben. Bliebe der Kern kleiner, nur auf einer Seite, sonst gar nicht.
  - *Ausgeschnitten* schneidet durch alle Schichten.
  - Öffnungen unter `OPENING_MIN_WALLS` × Mindestwand werden nur geschlossen.
  - *Mehrere Pakete:* Ein Füller kann in mehreren Paketen sitzen (Fenster über Eck: je Schenkel eine Öffnung, `detection.find_hosts`). Fehltreffer werden verworfen: Ein plattenartiger Füller muss parallel zum Paket liegen (± `HOST_PARALLEL_DEG`), bei Wänden muss der Teil mindestens 20 % der Füllerbreite und die halbe Höhe abdecken.
  - *Freie Öffnungen:* Fenster ohne Wandpaket (Loggia-Fenster, Fenster, deren IFC-Wirt ein anderes Fenster ist) erhalten eine eigene Platte. Sie wird nur gesetzt, wenn sie das Gebäude berührt (`windows.touches`).
- **Vernetzen:** Das Gitter wird per Marching Cubes vernetzt, geglättet (Taubin) und dezimiert (Quadric). Die Nachbearbeitung wird nur übernommen, wenn das Netz wasserdicht bleibt und sein Volumen hält (`DECIMATION_MAX_VOLUME_CHANGE`). Ob ein Teil wasserdicht ist, wird am exportierten STL (float32) geprüft, nicht nur am Netz im Speicher (`result.export_watertight`).
- **Landeskoordinaten:** Liegt ein Modell weit vom Ursprung (z.B. LV95, x ≈ 2 600 000 m), wird es beim Einlesen im Grundriss um ganze 100 m zum Ursprung verschoben (`IfcModel.offset_mm`, ab `OFFSET_THRESHOLD_MM`). STL und GLB speichern float32, das bei solchen Koordinaten nur 1 mm auflöst; ohne Versatz wären die Teile nach dem Export undicht.
- **Speicherbremse:** Vor dem Anlegen des Gitters wird seine Grösse gegen den Arbeitsspeicher geprüft (`shell.check_grid`, `BYTES_PER_VOXEL`, `GRID_RAM_RATIO`, Arbeitsspeicher über `psutil`, auf jedem Betriebssystem). Ist es zu gross, bricht die Erzeugung mit einem Hinweis ab (Qualität «entwurf», grösserer Massstab, Ausreisser). Ein Bauteil, das sich nicht voxelisieren lässt, wird übersprungen und mit GUID gemeldet.
- **Geschossfugen:** Das Gesamtmodell liegt in einem Gitter; jeder Voxel erhält ein Teil-Label (Geschoss, Dach oder Decke, `core/parts/`). Geschnitten werden nur Geschosse mit gedruckten Bauteilen. Die Fuge liegt an der Deckenunterkante, wo die Voxelzahl je Schicht am stärksten ansteigt; benachbarte Teile teilen so dieselbe Fläche und sind stapelbar. Ohne klare Deckenunterkante wird auf Geschoss-Z geschnitten und eine Warnung ausgegeben.
  - *Nur wo das Geschoss steht:* Die Fuge eines Geschosses gilt nur dort, wo dieses oder ein höheres Geschoss steht. Ein tieferer Gebäudeflügel wird nicht von der Fuge eines höheren geschnitten.
  - *Spalten ohne Geschoss:* Ausserhalb aller Grundrisse (Bauteile ohne Geschoss, Ränder unter dem Dach) gilt jede Fuge. Sonst fielen solche Spalten ans unterste Geschoss und gingen als Ganzes an ein Nachbarteil, auch weit unter dessen Boden.
  - *Eine Decke gehört zum Teil darüber (`storey_joints.flush_slabs`):* Ragt eine Decke, die bündig an der Fuge liegt, über den Grundriss des oberen Geschosses hinaus (Terrasse, Flachdach eines tieferen Flügels auf gleicher Höhe), gilt die Fuge auch dort. Das untere Teil bleibt oben offen, das obere hat eine ebene Unterseite. Wände, die durch die Fuge laufen, zählen nicht dazu.
  - *Fuge glätten (`storey_joints.smooth_joint`):* Die Unterseite des oberen Teils bleibt eben. Kleine Absätze unter der Fuge (z.B. Dämmung unter einer Decke, bis `JOINT_LEVELING_MM` = 150 mm real) werden abgeschnitten, kleine Rücksprünge darüber aufgefüllt. Tiefer liegende Deckenbereiche, die breiter als `JOINT_WIDTH_MM` = 2 m sind, werden nicht zerschnitten; schmale Unterzüge werden an der Fuge geschnitten. Durchgehende Abschnitte über `JOINT_SLAB_MM` = 1 m gelten als Wand.
  - *Tiefer liegende Decken als eigene Teile (`storey_joints.ceiling_lids`):* Eine Decke, die oben auf dem unteren Teil läge und unter der ein Raum dieses Teils liegt (z.B. TG-Dach neben dem Haus, tiefer als die Bodenplatte darüber), wird zum Teil «Decke <Geschoss>». Als Deckel bräuchte sie Stützen in den Räumen darunter, als eigenes Teil liegt sie flach auf dem Bett und wird aufgelegt. Geschnitten wird waagrecht an der häufigsten Deckenunterseite; Wände darunter bleiben beim unteren Teil, Wände bis `JOINT_WALL_MAX_MM` = 0.5 m zwischen zwei Deckenflächen gehören zum Deckel, schmalere Streifen (Stürze) bilden keinen. Mindestgrösse wie bei den Dächern (`ROOF_MIN_RATIO`).
  - *Unterseite eben (`storey_joints.flat_undersides`):* Als letzter Schritt der Aufteilung werden schmale Einstülpungen in der Unterseite jedes Geschossteils bis zur Fuge gefüllt: Storenkasten-Rinnen, Laibungsschlitze von Fenstern darunter, Fugen zwischen Bauteilen. Gefüllt wird nur, was schmaler als `JOINT_RECESS_WIDTH_MM` = 0.3 m und höchstens `JOINT_RECESS_DEPTH_MM` = 0.5 m tief ist; Treppenaugen, Schächte und tiefer liegende Decken bleiben offen, Dach- und Deckelteile unberührt. Jedes betroffene Teil meldet die Füllung im Bericht. Der Schritt läuft vor dem Vernetzen und vor den Steckverbindern, deren Taschen erst danach ins Netz geschnitten werden. Dazu die Regel `IfcBeam.LINTEL → fuellen` (1:500 bis 1:100): Die U-förmige Storenkasten-Einlage wird als Quader gedruckt, ihre Rinne kerbt die Decke nicht mehr ein; 1:50 behält das Detail.
  - *Dächer als eigene Teile:* Dachbauteile (`IfcRoof` samt seinen Teilen, `IfcSlab.ROOF`, `IfcCovering.ROOFING`, Unterklassen eingeschlossen) werden zum Teil «Dach <Geschoss>», wenn sie mehr als 5° geneigt sind oder als flaches Dach mehr als 1.5 m über der Kote ihres Geschosses liegen (`core/parts/roof.py`). Stäbe der Dachkonstruktion, die in der Dachzone liegen, kommen mit: `IfcBeam`, `IfcMember` und Dachbauteile, die keine Platte sind (ArchiCAD exportiert Sparren und Pfetten des Dachwerkzeugs als `IfcRoof` in Balkenform). Sonst hingen sie im Geschoss darunter frei in der Luft. Dachgruppen unter `ROOF_MIN_RATIO` (2 % des Volumens) bleiben normale Geschossbauteile.
  - *Inseln und Kleinteile:* Kleine abgetrennte Stücke eines Teils (unter `ISLAND_RATIO` = 25 % des Hauptstücks) gehen an das Nachbarteil mit der grössten Kontaktfläche. Lose Splitter ohne Kontakt entfallen; Stücke unter `SPECK_MIN_VOLUME_MM3`, die nur über Kanten hängen, werden vor dem Vernetzen entfernt. Ganze Teile unter 1 % des Volumens gehen an das angrenzende Teil. Das Ergebnis meldet, welche Teile aufgelöst wurden und wie viel Volumen verschoben oder abgeschnitten wurde.
  - *Geschlossene Hohlräume:* Hohlräume, die ein Teil ganz umschliesst (Schacht, Zwischenraum unter einem Bodenaufbau), werden bis `CAVITY_FILL_RATIO` = 5 % des Teilvolumens gefüllt. Sie sind nach dem Druck unsichtbar, bräuchten innen Stützen und würden im Slicer beim Trennen in Objekte zu Scheinkörpern. Grössere (z.B. ein geschlossener Dachraum) bleiben hohl; beides wird gemeldet.
- **Gefälle ebnen:** Decken, Dächer und Beläge, deren Oberseite überwiegend 0.3° bis 5° geneigt ist (`SLOPE_DEG`), werden im Voxelgitter eben gemacht: Jede Spalte wird von der tiefsten bis zur höchsten Schicht des Bauteils gefüllt. Die Decke wird dadurch um die Gefällehöhe dicker; das Ergebnis meldet die Anzahl.

Die Qualität bestimmt die Voxelgrösse (Pitch) und damit Laufzeit und Detailgrad. Der Aufwand wächst etwa kubisch mit 1/Pitch.

| Qualität | Pitch |
|---|---|
| fein | 0.4 mm |
| entwurf | 0.8 mm |
| auto | fein, ausser das Gitter wäre zu gross für den Arbeitsspeicher (`AUTO_GRID_RATIO`), dann entwurf |

### Überhänge

Nach dem Aufteilen prüft `core/parts/overhangs.py` jedes Teil so, wie es gedruckt wird (unterste Schicht auf dem Bett). Ein Voxel ist getragen, wenn in der Schicht darunter er selbst oder ein Nachbar zum selben Teil gehört (45°-Regel). Ungetragene Stellen sind Brücken, wenn getragenes Material höchstens `BRIDGE_MAX_MM` / 2 = 5 mm entfernt ist, sonst brauchen sie Stützen. Unterschieden wird, ob die Stützen auf dem Bett stehen (leicht zu entfernen) oder auf dem Modell (z.B. unter einer Decke über Räumen).

- **Meldung je Teil** ab `OVERHANG_MIN_MM2` = 25 mm²: Stützfläche, davon über dem Modell, grösste Stelle (Masse, Höhe über dem Bett, Bauteil) und ein Vorschlag: «Stützen nur vom Druckbett aus genügen» oder, wenn mindestens `OVERHANG_ON_MODEL_RATIO` = 50 % über dem Modell liegen, «Bauteil dem Teil darüber oder dem Dachteil zuordnen». Ohne Stützbedarf eine Zeile «alle Teile ohne Stützen druckbar». Die Meldungen stehen in den Warnungen und im PDF-Report, die Kennzahl «Stützfläche (cm²)» bei den Kennzahlen.
- **Rot im Viewer:** Die Stützflächen erscheinen in der STL-Ansicht als rote Flächen im Teil (zusammengefasste Quader, im selben GLB wie das Teil, daher folgen sie dem Ausblenden und «auseinander»).

### Steckverbinder

Optional (Setup, erlaubt ab 1:200): Wo das untere Teil die Decke darüber trägt (Wandkronen, Stützenköpfe), entstehen je Fuge drei Zapfen als Kegelstumpf auf der Krone und passende Taschen in der Deckenunterseite (`core/connectors/`). Drei Punkte lassen das obere Teil statisch bestimmt aufliegen; es wird nur aufgesetzt, nicht eingerastet. Auf länglichen Kontaktflächen (Wände) sind die Zapfen rechteckig, auf gedrungenen (Stützen, Ecken) rund. Das Passungsspiel kommt aus dem Druckerprofil (`clearance_mm`, Standard 0.20 mm). Ist eine Krone zu schmal oder eine Decke zu dünn, meldet das Ergebnis die Fuge.

---

## Leistung

Testrechner mit 4 Kernen und 15 GB RAM, Qualität fein, Massstab 1:200, Fenster und Türen vertieft. Gemessen am 21.10.2026 vor und nach der Optimierung von Leistung und Speicher.

| Modell / Kennzahl | Vorher | Nachher |
|---|---|---|
| `MFH_eBKPH_Test.ifc`: Erzeugen · Spitzenspeicher | 24 s · 1.1 GB | 14.6 s · 1.1 GB |
| `MFH_eBKPH_Real.ifc`: Erzeugen · Spitzenspeicher | 23.3 s · 1.6 GB | 17.6 s · 1.1 GB |
| `ARC_Modell_NEST_230328.ifc`: Erzeugen · Spitzenspeicher | 150 s · 6.3 GB | 83 s · 3.8 GB |
| NEST: Download «STL komplett» | 10.8 GB Speicherspitze | 5 s, ohne Neuvernetzen |
| NEST: STL nach dem Export wasserdicht | nein (LV95, float32 auf 1 mm) | ja |

Die Aufteilung des Codes in kleinere Module und die englischen Namen (Oktober 2026) haben die Ergebnisse nicht verändert: `scripts/baseline_metrics.py --all --compare` liefert über alle Testmodelle dieselben Werte wie davor.

Reales ArchiCAD-Modell 4503 (Export vom 20.10.2026, 1:200, fein): 10 Teile (98 TG inkl. Bodenplatte und Fundamente, Decke 98 TG in zwei Stücken, 99 UG, 00 EG, 01 OG, 02 OG, Dach 02 OG, 03 DG, Dach 03 DG). Beide Mansarddächer sind eigene Teile samt Sparren und Pfetten der Dachkonstruktion (95 `IfcRoof` in Balkenform auf «045 Dachkonstruktionen»). Das TG-Dach neben dem Haus liegt 0.4 m tiefer als die Bodenplatte des UG und ist ein eigenes, flach druckbares Teil; vorher lag es als Deckel auf dem TG und brauchte 43 cm² Stützen in der Garage (jetzt 4 cm²). Vier geschlossene Hohlräume (u.a. ein Schacht von 10 × 10 × 12 mm) werden gefüllt; vorher machte der Slicer daraus beim Trennen vier Scheinobjekte. 47 Bauteile werden als Umgebung erkannt (darunter die «Aussenwände EG» auf dem Layer «011 Stützwände»), alle Türen und Fenster sind beidseitig vertieft. Die verbleibenden Stützen (TG 108 cm², UG 12 cm²) liegen unter der gestuften Bodenplatte und stehen auf dem Bett.

Überhang-Test, Deckenteile und Hohlräume (23.10.2026, Cloud-Rechner mit 4 Kernen, 15 GB RAM, je ein Lauf alt und neu hintereinander): Erzeugen 4503 122.4 s → 122.0 s, Spitzenspeicher 3.44 → 3.41 GB; NEST 125.3 s → 119.2 s, 3.77 GB unverändert. Die Unterschiede liegen im Messrauschen.

Wanddicken im erzeugten Gitter (`scripts/wall_thicknesses.py`, NEST, Qualität fein):

| Wandtyp (real) | 1:200 vorher | 1:200 nachher | 1:100 nachher |
|---|---|---|---|
| IW_Ortbeton 0.15 m | 1.2 oder 1.6 mm gemischt | 1.2 mm | 1.6 mm |
| IW_Ortbeton 0.16 m | 0.8 mm | 1.2 mm | 1.6 mm |
| IW_Ortbeton 0.18 m | 0.8 mm | 1.2 mm | 2.0 mm |
| Aussenwand-Paket (Beton 0.25 + Dämmung 0.20 + Panel 0.02 m) | zu dick (Panel einzeln aufgedickt) | 2.4 mm (Ziel 2.35) | – |

---

## Entwicklungsumgebung

| Bereich | Werkzeug |
|---|---|
| Sprache | Python 3.11 oder neuer (getestet mit 3.13) |
| Umgebung | Virtuelle Umgebung (venv) |
| Versionsverwaltung | Git, GitHub |
| Editor | VS Code |
| Tests | pytest, 291 Tests (Architektur, core, db, Oberfläche mit simuliertem Nutzer, Skripte) |

Verwendete Bibliotheken (aus `requirements.txt`):

| Bibliothek | Zweck |
|---|---|
| ifcopenshell | IFC lesen, triangulieren |
| numpy | Voxelmatrizen, vektorisierte Berechnungen |
| pandas | Bauteiltabelle |
| scipy | Morphologie (Hohlräume füllen, verdicken), orientierte Bounding-Box |
| scikit-image | Marching Cubes |
| trimesh, manifold3d | Meshes, STL- und GLB-Export, Booleans der Steckverbinder |
| fast-simplification | Quadric-Dezimierung (von trimesh genutzt) |
| matplotlib | Modellbild im PDF-Report |
| jinja2, weasyprint | PDF-Report: HTML-Template und Satz als PDF (Seitenumbruch, wiederholter Tabellenkopf) |
| psutil | Arbeitsspeicher für die Speicherbremse |
| nicegui | Oberfläche inkl. 3D-Viewer (`ui.scene`) |
| fastapi | Route für die GLB-Dateien des Viewers (kommt mit nicegui) |
| pytest, pytest-asyncio | Tests |

Bezug zu den Vorgaben des Leistungsnachweises:

| Vorgabe | Umsetzung |
|---|---|
| IfcOpenShell | IFC-Import und Triangulierung (`core/ifc/`) |
| Pandas | Bauteiltabelle, Regelanwendung, Druckbarkeitsprüfung |
| Matplotlib | Modellbild (isometrische 3D-Ansicht der Druckteile) im PDF-Report (`core/output/report_image.py`) |
| SQLite | Regeln, Massstab-Parameter, Druckerprofile, Material, Exportverlauf (`db/`) |
| NiceGUI | Oberfläche und 3D-Viewer (`ui/`) |

---

## Grenzen

- Die Ausrichtung macht nur das dominante Wandsystem achsparallel. Ein zweites, schräg stehendes System (z.B. ein abgewinkelter Flügel) bleibt leicht gestuft.
- Wanddicken werden auf ganze Voxel gerundet (Paketdicke, mindestens 1.2 mm bei 1:200): Bei «fein» (0.4 mm) weicht eine Wand bis zu 0.2 mm von der massstäblichen Dicke ab, dafür sind gleiche Wandtypen überall gleich dick.
- Stützen und Träger werden allseitig aufgedickt und nicht auf Voxel gerastet.
- Filament, Kosten und Druckzeit sind Schätzungen mit Faustwerten aus `config.py` (`VOLUME_FACTOR`, `THROUGHPUT_CM3_H`, `LAYER_CHANGE_H`), nicht mit Slicer-Werten abgeglichen.
- Fenster und Türen werden als schlichte Füllkörper umgesetzt, die Laibung ist eine flache Vertiefung. Vordefinierte Fenstertypen sind nicht umgesetzt.
- Dachteile mit geschlossener Haut (Deckel) brauchen beim aufrechten Druck Stützmaterial; die Teile werden nur um die Hochachse gedreht, nicht gekippt.
- Das Gefälle-Ebnen macht Decken und Dächer um die Gefällehöhe dicker (Volumen und Filament steigen leicht).
- Die Umgebungserkennung hängt von Namen, Typnamen und Layern des Modells ab. Falsch erkannte oder übersehene Bauteile lassen sich je Bauteil übersteuern.
- Die Fugenglättung nutzt feste Schwellen (`JOINT_*`, `ISLAND_RATIO`, `ROOF_*`, `HOST_*`, alle mit Begründung in `config.py`), die am ArchiCAD-Modell 4503 abgestimmt sind; andere Modelle können Anpassungen brauchen.
- «STL komplett» ist ein Mehrkörper-STL aus den Geschossteilen (sie berühren sich an den Fugen); der Slicer zeigt mehrere Körper.
- Doppelte Geschossnamen (zwei Gebäude mit je einem «EG») werden mit dem Gebäudenamen unterschieden, notfalls nummeriert; jedes wird ein eigenes Teil.
- 3MF-Export und die übrigen Ausgabeziele (Resin, Lasercut, Web) sind nicht umgesetzt (in der unteren Leiste als «bald» angelegt).

---

## Projektstruktur

```
IFC2Print/
├─ main.py                    # Startpunkt
├─ app.py                     # Seite registrieren, NiceGUI starten
├─ config.py                  # Fachkonstanten mit Begründung
├─ requirements.txt
├─ pyproject.toml             # Projektdaten und pytest-Konfiguration
├─ README.md
├─ assets/                    # Logo und Favicon
├─ core/                      # Verarbeitung (ohne Oberfläche)
│  ├─ pipeline.py             #   Fassade für Oberfläche, Skripte, Tests
│  ├─ generation.py           #   Ablauf der Erzeugung
│  ├─ ifc/                    #   IFC einlesen
│  ├─ analysis/               #   Regeln, Umgebung, Druckbarkeit, Prüfpunkte
│  ├─ packages/               #   Wandpakete
│  ├─ voxels/                 #   Voxelgitter und Vernetzen
│  ├─ openings/               #   Fenster und Türen
│  ├─ parts/                  #   Geschoss-, Dach- und Deckenteile, Überhänge, Druckbett
│  ├─ connectors/             #   Steckverbinder
│  └─ output/                 #   Ergebnis, Report, Kalkulation, Viewer-Daten
├─ db/
│  ├─ database.py
│  ├─ schema.sql
│  └─ seed/                   # regeln.csv, massstaebe.csv, profile.csv, material.csv
├─ ui/                        # NiceGUI-Oberfläche: page.py, ein Blatt je sheet_*.py, panel, viewer …
├─ scripts/                   # generate_stl, baseline_metrics, wall_thicknesses, diagnostics
├─ tests/                     # pytest (Architektur, core, db, Oberfläche, Skripte)
├─ testdaten/                 # IFC-Testmodelle
├─ docs/                      # Designbriefing ZP1, Massstab-Regelwerk
└─ output/                    # erzeugte Dateien (nicht im Repository)
```

`db/regeln.db` wird beim ersten Start aus `db/seed/` erzeugt und nicht eingecheckt.

---

## Weitere Dokumente

Die Dokumente in `docs/` beschreiben frühere Arbeitsstände und verwenden teilweise noch die deutschen Datei- und Funktionsnamen von vor Oktober 2026.

| Dokument | Inhalt |
|---|---|
| `docs/MASSSTAB_REGELWERK.md` | Konzept der Regelwerke je Massstab |
| `docs/IFC2Print_ZP1_Designbriefing_v2.md` | Designbriefing zur Zwischenpräsentation 1 (ZP1) |
