# Design-Briefing v2: IFC2Print – ZP1 (Variante A «Slicer», vertieft)

**An:** Claude Design · **Von:** Gian Blaser · HSLU Digital Construction · Modul Programmieren
**Termin:** ZP1, Mo 26.10.2026 · **Redezeit:** 5 min · **4 Folien** (+ Titelfolie, 10 s)
**Format:** 16:9, 1920 × 1080 px, Endexport **PPTX** · **Sprache:** Schweizer Standarddeutsch, nie «ß»

> **Auftrag:** Setze genau diese Folien um. Texte wörtlich übernehmen, keine Texte ergänzen.
> **Verboten:** Icons, Emojis, Piktogramme, Clipart, Stockfotos, Logos, Aufzählungszeichen-Symbole, Verläufe in Regenbogenfarben.
> **Erlaubt und erwünscht:** grosse, hochwertige, gerenderte Bilder (Prompts in Kap. 4), echte Screenshots, typografische Grafiken aus Linien, Flächen und Code.

---

## 1. Dramaturgie: Eine Folie, eine Aussage

Das Publikum soll nachher einen Satz kennen: **«IFC2Print macht aus einem BIM-Modell automatisch einen druckbaren Körper.»**

| # | Leitfrage | Kernaussage (= Folientitel) | Bildidee |
|---|---|---|---|
| 0 | Was ist das? | `IFC2Print` | Gebäude halb BIM, halb gedruckt |
| 1 | Warum? | `1206 Bauteile. Null druckbar.` | Gebäude zerfällt in Einzelteile über dem Druckbett |
| 2 | Wie ist der Code gebaut? | `Gebaut wie ein Haus: Schicht für Schicht.` | Explosionszeichnung: jedes Geschoss = ein Python-Modul |
| 3 | Was ist der Kniff? | `Der Trick: Würfel statt Flächen.` | Gebäude aus Voxeln + echter Codeausschnitt + Kennzahlen |
| 4 | Wo stehe ich, was folgt? | `Fundament steht. Jetzt wird aufgestockt.` | Repo als Gebäudeschnitt + Fortschritt |

Der rote Faden läuft über alle Folien: **Das Gebäude wird gedruckt.** Folie 1 zeigt es zerlegt, Folie 2 in Schichten, Folie 3 als Voxelkörper und Folie 4 im Aufbau.

---

## 2. Globales Design-System

### 2.1 Farben
| Token | Hex | Einsatz |
|---|---|---|
| `bg` | `#0F1114` | Hintergrund |
| `panel` | `#1A1D23` | Code-Panels, Flächen |
| `grid` | `#262A31` | Druckbett-Raster |
| `text` | `#F2F3F5` | Haupttext |
| `muted` | `#9AA1AB` | Sekundärtext (nie kleiner als 24 px) |
| `petg` | `#FF6B2C` | Einziger Akzent: gedrucktes Material, Schlüsselwörter |
| `ifc` | `#5AA9FF` | BIM / IFC / «noch nicht gedruckt» |
| `ok` | `#3DDC97` | nur für «wasserdicht ✓» und «GO» |

Regel: Pro Folie höchstens **ein** orange hervorgehobenes Schlüsselwort im Titel.

### 2.2 Typografie (Mindestgrössen – nichts kleiner)
| Rolle | Schrift | Grösse | Gewicht |
|---|---|---|---|
| Titel | Inter | **72 px** | 800, Laufweite −1 % |
| Kicker | JetBrains Mono | 24 px, VERSALIEN, +10 % | 600, `petg` |
| Statement / Text | Inter | **36 px** | 500 |
| Grosse Zahl | JetBrains Mono | **120 px** | 700 |
| Zahl-Label | Inter | 26 px | 500, `muted` |
| Code | JetBrains Mono | **28 px**, Zeilenabstand 1.4 | 400 |
| Beschriftung an Grafik | JetBrains Mono | 26 px | 500 |
| Fussleiste | JetBrains Mono | 22 px | 500 |

PPTX-Fallback: Segoe UI / Consolas.
**Textregeln:** max. **8 Wörter pro Satz**, max. **3 Textzeilen pro Block**, max. **30 Wörter pro Folie** (Code und Zahlen ausgenommen). Keine Aufzählungspunkte, Struktur entsteht über Position und Grösse.

### 2.3 Raster
- 1920 × 1080, Ränder 96 px seitlich, 80 px oben, 88 px unten.
- Kopf: Kicker y 80, Titel y 120–210.
- Inhalt: y 260–940.
- Fussleiste: y 980–1030.
- Asymmetrisch: Bild/Grafik nimmt immer **≥ 55 % der Fläche** ein, darf randabfallend sein (bis an den Folienrand).

### 2.4 Hintergrund
- `bg` vollflächig.
- Druckbett-Raster (`grid`, 1 px, 48 px Abstand) **nur unter der Hauptgrafik**, radial ausgeblendet (Mitte 70 % Deckkraft → Rand 0 %). Kein Raster unter Text.

### 2.5 Fussleiste «Layer-Balken» (alle Folien 1–4)
- Links: `IFC2Print · Gian Blaser` (`muted`).
- Mitte x 700–1420: Balken 12 px hoch, Hintergrund `panel`, Füllung `petg`. Füllgrad 25 / 50 / 75 / 100 %.
- Rechts davon: `LAYER 1/4`, `2/4`, `3/4`, `4/4` (`text`).
- Keine Seitenzahlen, kein Logo.

### 2.6 Übergänge
- Folienübergang **«Schieben» nach oben**, 0.5 s.
- Pro Folie genau **eine** Klick-Animation (unten pro Folie definiert), Typ «Einblenden» oder «Wischen», 0.4 s.

---

## 3. Folien im Detail

### Folie 0 – Titel (10 s)
- **Bild:** Render R0 (Kap. 4), randabfallend, rechte 65 % der Folie (x 670–1920, volle Höhe).
- **Links, vertikal zentriert, x 96–700:**
  - Kicker: `MODUL PROGRAMMIEREN · ZP1`
  - Titel 140 px, 800: `IFC2Print`
  - Darunter 40 px, `muted`: `Vom BIM-Modell`
  - Nächste Zeile 40 px, `petg`: `aufs Druckbett.`
  - Unten links, 24 px, `muted`: `Gian Blaser · 26.10.2026`
- Keine Fussleiste.

---

### Folie 1 – Problem (0:50)
- **Kicker:** `LAYER 1 · DAS PROBLEM`
- **Titel:** `1206 Bauteile. Null` + `druckbar.` (das Wort «druckbar.» in `petg`)
- **Bild:** Render R1, randabfallend rechts, x 760–1920, y 230–970.
- **Linke Spalte x 96–700: drei Zahlen-Blöcke übereinander**, je Zahl 120 px + Label 26 px, Abstand 40 px. Zahlen in `ifc`:

  | Zahl | Label (2 Zeilen max.) |
  |---|---|
  | `592` | `Bauteile ohne Geometrie` |
  | `0.1 mm` | `Glas bei 1:200. Die Düse druckt 0.4 mm.` |
  | `≠ dicht` | `Bauteile überschneiden sich. Der Slicer streikt.` |

- **Klick-Animation:** Die drei Zahlen erscheinen nacheinander (Einblenden, Abstand 0.2 s).
- **Sprechtext:** «Das BIM-Modell gibt es schon. Drucken kann man es nicht. Über die Hälfte der Bauteile hat keine Geometrie. Glas wird im Massstab dünner als die Düse. Und das Netz ist nicht dicht. Mein Ziel: ein Tool, das das automatisch löst.»

---

### Folie 2 – Code-Architektur (1:30)
- **Kicker:** `LAYER 2 · DER CODE`
- **Titel:** `Gebaut wie ein Haus:` + `Schicht für Schicht.` (zweiter Teil `petg`)
- **Hauptgrafik (x 96–1300, y 250–960): Explosions-Axonometrie.** Fünf flache, übereinander schwebende Platten (isometrisch, je 900 × 90 px Ansicht, vertikaler Abstand 40 px), gestaltet als **gedruckte Geschossplatten** mit sichtbaren horizontalen Layerlinien (feine Linien alle 4 px auf der Plattenkante). Unterste Platte = Daten-Eingang, oberste = Ausgabe. Feine vertikale Fluchtlinien (`grid`, gestrichelt) verbinden die Platten.
  Farbverlauf der Platten von unten `ifc` (Rohdaten) nach oben `petg` (druckbar), 5 Stufen linear interpoliert.
  Rechts jeder Platte, auf gleicher Höhe, Beschriftung in zwei Zeilen:
  Zeile 1 (JetBrains Mono 30 px, `text`): Dateiname
  Zeile 2 (Inter 26 px, `muted`): Aufgabe

  | Ebene (unten → oben) | Zeile 1 | Zeile 2 |
  |---|---|---|
  | 1 | `ifc_modell.py` | `liest IFC, baut Netze` |
  | 2 | `regelwerk.py` | `behalten · verdicken · entfernen` |
  | 3 | `druckbarkeit.py` | `0.8 mm Wand? Passt in Bauraum?` |
  | 4 | `huelle.py` | `Voxel-Hülle, wasserdicht` |
  | 5 | `app.py` | `Streamlit-Oberfläche` (Platte nur als gestrichelte Kontur `petg` = in Arbeit) |

- **Rechte Spalte x 1360–1824, y 300–900: Code-Panel `panel`**, Ecken 16 px, Innenabstand 32 px. Titelzeile 22 px `muted`: `config.py`. Inhalt Code 28 px (Syntaxfarben: Variablen `text`, Zahlen `petg`, Kommentare `muted`):
  ```
  DUESE_MM       = 0.4
  MINDESTWAND_MM = 0.8
  VOXEL_PITCH_MM = 0.4
  MASSSTAB       = 200
  ```
  Darunter 26 px `muted`: `Ein Ort für alle Druckerwerte.`
- **Klick-Animation:** Platten erscheinen von unten nach oben («Wischen» von unten), wie ein Druck.
- **Sprechtext:** «Der Code ist aufgebaut wie ein Haus. Jedes Geschoss ist ein Modul mit genau einer Aufgabe. Unten wird das IFC gelesen. Das Regelwerk entscheidet pro IFC-Klasse: behalten, verdicken oder entfernen – so funktioniert es mit jedem Modell, ohne eBKP-H. Dann Druckbarkeit, dann die Hülle. Alle Druckerwerte stehen zentral in config.py.»

---

### Folie 3 – Der Kniff + Beweis (1:20)
- **Kicker:** `LAYER 3 · DER KNIFF`
- **Titel:** `Der Trick:` + `Würfel statt Flächen.` (zweiter Teil `petg`)
- **Linke Hälfte x 0–960 (randabfallend links), y 230–980:** Render R3 (Voxel-Gebäude).
  Über dem Bild, unten links, Bildlegende 26 px auf halbtransparentem `bg` (80 %): `0.4 mm Würfel = eine Düsenbreite`
- **Rechte Hälfte x 1020–1824:**
  - **Oben (y 250–560): Code-Panel** `panel`, Titelzeile `core/huelle.py`, Code 28 px, die Kernzeile `binary_fill_holes` mit linkem 6-px-Balken `petg` markiert:
    ```
    vox = mesh.voxelized(pitch=0.4)
    voll = binary_fill_holes(vox.matrix)
    # pro Bauteil – Räume bleiben hohl
    ```
    Darunter 26 px `muted`, 2 Zeilen: `Parallel auf allen CPU-Kernen.` / `Ergebnis: immer wasserdicht.`
  - **Unten (y 600–940): Kennzahlen-Reihe**, 3 Spalten, je Zahl 96 px + Label 24 px:

    | Zahl | Label |
    |---|---|
    | `4.7 Mio.` | `Voxel` |
    | `469 s` | `Laufzeit` |
    | `✓` (in `ok`, 120 px) | `wasserdicht` |

  - Oben rechts im Kopfbereich (x 1600, y 80): **Stempel** Kreis Ø 160 px, Rand 5 px `ok`, gedreht −10°, innen `GO` (JetBrains Mono 56 px `ok`) und `12.10.` (24 px). Typografisch, kein Icon.
- **Klick-Animation:** Stempel «GO» erscheint.
- **Sprechtext:** «Der wichtigste Entscheid: Ich rechne nicht mit Flächen, sondern mit Würfeln von 0.4 Millimetern – genau eine Düsenbreite. Jedes Bauteil wird einzeln gefüllt, so bleiben die Räume hohl. Mein erster Versuch füllte das ganze Haus auf; das habe ich so gelöst. Ergebnis: 4.7 Millionen Voxel, wasserdicht, Machbarkeit bewiesen. Die Laufzeit optimiere ich als Nächstes.»

---

### Folie 4 – Repository + Roadmap (1:20)
- **Kicker:** `LAYER 4 · REPO & ROADMAP`
- **Titel:** `Fundament steht.` + `Jetzt wird aufgestockt.` (zweiter Teil `petg`)
- **Linke Hälfte x 96–900: Repository als Gebäudeschnitt.** Ein hoher, schmaler Gebäudeschnitt (Rechteck 700 × 660 px, y 260–920), unterteilt in 5 Geschosse (horizontale Linien 2 px `text`). In jedem Geschoss steht der Ordnername (JetBrains Mono 30 px) links und die Funktion (26 px `muted`) rechts:

  | Geschoss (unten → oben) | Ordner | Funktion | Füllung |
  |---|---|---|---|
  | UG | `testdaten/` | `IFC-Modelle` | `panel` |
  | EG | `core/` | `Fachlogik` | `petg` 100 % |
  | 1. OG | `tests/` | `pytest, 10 Tests` | `petg` 70 % |
  | 2. OG | `scripts/` | `Stufe-0-Lauf` | `petg` 100 % |
  | Dach | `app.py` | `Streamlit` | nur Kontur gestrichelt `petg` |

  Seitlich links am Schnitt eine Höhenkote, typografisch: `▽ venv · requirements.txt` auf Höhe Boden.
  Über dem Dach 26 px `muted`: `_parkiert/ – Code für Stufe 2–3, bereit`

- **Rechte Hälfte x 980–1824: Roadmap als Druckfortschritt.** Vertikaler Balken (x 1000, Breite 24 px, y 260–920), unten `petg` gefüllt bis 25 % der Höhe, darüber `panel`. Auf dem Balken 4 Marken (Linie 40 px nach rechts), rechts daneben Text:

  | Höhe | Datum (JetBrains Mono 30 px) | Inhalt (Inter 30 px) |
  |---|---|---|
  | 25 % (orange, aktuelle Position) | `12.10.` | `Machbarkeit ✓` |
  | 45 % | `26.10.` | `Regelwerk + Oberfläche` |
  | 70 % | `KW 47–48` | `SQLite + Report` |
  | 100 % | `MEP` | `Geschosse + Steckverbinder` |

  Die Marke bei 25 % trägt ein orangefarbenes Dreieck (Düse) – rein grafisch, 24 px.

- **Unten über die ganze Breite (y 880–940): GitHub-Zeile** ohne Box, JetBrains Mono 32 px:
  `github.com/GianBlaser/HSLU_GB_26` (`text`) + Abstand + `→ öffentlich` (`petg`). Daneben rechts QR-Code 120 × 120 px, weiss auf `bg`, Ziel https://github.com/GianBlaser/HSLU_GB_26.
- **Klick-Animation:** Der orange Fortschrittsbalken «wächst» von 0 auf 25 % (Wischen von unten).
- **Sprechtext:** «Das Repository ist gleich aufgebaut wie das Programm: Fachlogik in core, Tests in tests, das Machbarkeitsskript in scripts. Die Umgebung läuft mit venv und einer requirements-Datei, alles versioniert auf GitHub. Bis heute in zwei Wochen kommen Regelwerk und Streamlit-Oberfläche, danach SQLite, Report und am Ende geschossweise Teile mit Steckverbindern.»

---

## 4. Gerenderte Bilder (Bild-Prompts)

Einheitlicher Look für alle Renders: **dunkles Studio, eine weiche Lichtquelle von links oben, geringe Schärfentiefe, fotorealistisch, Blickwinkel 30° von oben, Farbpalette nur Anthrazit, PETG-Orange `#FF6B2C`, kühles Blau `#5AA9FF`.** Kein Text im Bild, keine Logos, keine Menschen.

**R0 – Titel**
> Photorealistic studio render of a modern 4-storey apartment building model on a dark textured 3D-printer bed. The lower half is a physical orange PETG print with fine visible horizontal layer lines and a subtle glossy sheen. The upper half dissolves into a glowing thin blue wireframe (BIM model). A printer nozzle hovers exactly at the transition line, a hot orange glow at its tip. Dark anthracite background, soft key light from top left, shallow depth of field, 16:9, cinematic, high detail, no text.

**R1 – Problem**
> Photorealistic render of an architectural BIM building model exploded into hundreds of separate floating parts — walls, slabs, glass panes, window frames, columns — hovering chaotically above an empty dark 3D-printer bed with a fine grid. Parts rendered as translucent blue glass-like elements with thin glowing edges; some glass panes paper-thin. Dark anthracite background, dramatic soft light, sense of disorder, 16:9 vertical crop focus on right side, no text.

**R3 – Voxel**
> Photorealistic macro render of a small building model made entirely of tiny orange PETG cubes (voxels), clearly visible stepped cube edges on the roof and facade, interior rooms hollow and visible through a cut section. Sits on a dark printer bed. One corner transitions from smooth blue wireframe into the orange voxel blocks. Soft studio light from top left, dark anthracite background, shallow depth of field, 16:9, no text.

**Fallback, falls keine Bildgenerierung möglich ist** (Gian liefert die Bilder dann selbst):
- R0 → Gian rendert `output/Box_1_200_P0_V03.stl` in PrusaSlicer (Vorschau «Höhe», Druck auf halber Höhe gestoppt) oder in Blender.
- R1 → Screenshot des IFC in einem IFC-Viewer, Explosionsansicht.
- R3 → `docs/vergleich_voxel_alt_neu.png` bzw. Nahaufnahme der Voxel-STL.
Platzhalter: Fläche `panel`, Dateiname zentriert 26 px `muted`.

---

## 5. Abnahme-Checkliste für Claude Design
- [ ] 5 Folien (0–4), nur Variante A
- [ ] Kein Icon, kein Emoji, kein Stockfoto. Einzige Symbole: «✓», «▽» und das Düsen-Dreieck
- [ ] Keine Schrift unter 22 px, kein Fliesstext unter 26 px
- [ ] Kein Satz über 8 Wörter, keine Folie über 30 Wörter (ohne Code/Zahlen)
- [ ] Bilder bzw. Grafiken nehmen ≥ 55 % der Fläche ein
- [ ] Pro Folie genau eine Klick-Animation
- [ ] Zahlen exakt: 1206 · 592 · 0.1 mm · 0.4 mm · 0.8 mm · 4.7 Mio. · 469 s
- [ ] Sprechtexte in den PPTX-Notizen
- [ ] Grafiken als editierbare Formen, Renders als Bilder
- [ ] Export PPTX 16:9, Fallback-Schriften Segoe UI / Consolas
