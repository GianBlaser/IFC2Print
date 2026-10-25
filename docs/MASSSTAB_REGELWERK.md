# Massstab-Regelwerk – Spezifikation

Stand 22.10.2026 · Grundlage für die Umsetzung mit Claude Code · Entscheide mit Gian geklärt

## 1. Ziel

Heute gibt es in «02 Setup» zwei unabhängige Auswahlen: **Regelset** (Dropdown, DB) und **Massstab** (Segmente,
`config.MASSSTAEBE`). Künftig gibt es **nur noch den Massstab**. Dahinter liegt pro Massstab ein vollständiges
Regelwerk aus

1. **Klassenregeln** – IFC-Klasse → Aktion (wie heute `regel`-Tabelle), und
2. **Parametern** – alles, was heute fix in `config.py` steht, aber vom Massstab abhängt
   (Mindestdicken, Laibung, erlaubte Qualität, Steckverbinder, Öffnungs-Defaults, Relief).

Angeboten werden genau die vier Stufen **1:50, 1:100, 1:200, 1:500** (keine freien Massstäbe).

## 2. Entscheide

| # | Thema | Entscheid |
|---|---|---|
| 1 | Freie Massstäbe | Nein, nur die 4 Stufen. Die Bauraum-Empfehlung rundet auf die nächste Stufe. |
| 2 | 1:500 Aufteilung | **Pro Geschoss** wie die anderen (Innenwände bleiben: sie tragen die Decken, Stützmaterial im Gebäude ist keine Option). |
| 3 | 1:500 Sockel/Gelände | Vorerst nichts. |
| 4 | Auskragungen (Balkone, Vordächer) | Werden gedruckt, Stützmaterial ist akzeptiert. Keine Erkennung über Namen. |
| 5 | Geländer | Werden als **dünne Scheibe** gedruckt, vom Boden bis zur Geländerhöhe (≈ 1.0–1.2 m). Neue Aktion `band`. |
| 6 | Wanddicke über dem Minimum | Originaldicke (skaliert) bleibt erhalten, nur dünnere Wände werden aufgedickt. **Ist bereits umgesetzt** (siehe 3). |
| 7 | Zusätzliche Kategorien 1:100/1:50 | Nur **Relief der Vorhangfassade** (Pfosten/Riegel bzw. Feldformen), stützenfrei druckbar. Übrige Ideen (Sonnenschutz, Möbel, freier Stahlbau) vorerst nicht. |
| 8 | 1:50 Einsatz | Ausschnitte (einzelne Geschosse, später Räume). Voxelgrösse automatisch auf 0.8 mm, wenn 0.4 mm zu gross wird. |

## 3. Befund Wanddicke (Entscheid 6) – bereits vorhanden

`core/pakete.skalierung()`:

```python
gerundet = int(np.floor(alt / pitch_mm + 0.5 + 1e-6))
voxel = max(int(np.ceil(mindestdicke_mm / pitch_mm - 1e-9)), gerundet)
```

Ein Wandpaket behält also seine skalierte Originaldicke, gerundet auf ganze Voxel (±½ Voxel: ±0.2 mm bei «fein»,
±0.4 mm bei «entwurf»), und wird nur unter der Mindestdicke aufgedickt. Schräge Pakete behalten die exakte Dicke
(`max(alt, mindestdicke)`). Stützen/Träger: `huelle.verdickung_voxel()` gibt 0 zurück, sobald die Dicke ≥ Mindestwand.

**Zu ändern ist nur die Quelle der Mindestdicke:** `pipeline._mindestdicke()`, `pipeline._oeffnungen()`
(`mindest_frei`) und `pipeline.paket_mindestdicke()` lesen heute `config.MINDESTDICKE_WAND_MM` (fix 1.2) und
sollen künftig den Massstab-Parameter verwenden. Dazu Tests (siehe 10).

Hinweis Entwurf (0.8-mm-Voxel): 1.2 mm wird auf 2 Voxel = **1.6 mm** aufgerundet. Das ist so gewollt (Wände dürfen nie
dünner als das Minimum werden), muss aber in der Oberfläche erklärt werden.

## 4. Parameter pro Massstab

Werte im Modellmass (mm). Die wirksame Dicke ist immer `max(Profil.mindestwand_mm, Massstab-Parameter)`:
das Druckerprofil bleibt die physikalische Grenze, das Regelwerk die gestalterische.

| Parameter | 1:500 | 1:200 | 1:100 | 1:50 | Bemerkung |
|---|---|---|---|---|---|
| `mindestdicke_wand_mm` | **0.8** | 1.2 | 1.2 | 1.2 | 0.8 = 2 Perimeter, 1.2 = 3 |
| `mindestdicke_gelaender_mm` | – | 0.8 | 0.8 | 0.8 | Aktion `band` |
| Decken/Dächer/Stützen | Profil | Profil | Profil | Profil | unverändert (`profil.mindestwand_mm`, 0.8) |
| `laibungstiefe_mm` | 0.4 | 0.4 | 0.8 | 1.6 | real ≈ 8 cm (1:500: 20 cm = 1 Voxel) |
| `mindestkern_laibung_mm` | 0.4 | 0.4 | 0.4 | 0.4 | |
| `qualitaeten` | fein | fein, entwurf, auto | fein, entwurf, auto | fein, entwurf, auto | |
| `qualitaet_default` | fein | fein | fein | **auto** | auto: siehe 7.3 |
| `verbinder_erlaubt` | **0** | 1 | 1 | 1 | Zapfen min. 1.2 mm passen nicht in 0.8-mm-Wände |
| `fenster_default` / `tuer_default` | vertieft | vertieft | vertieft | vertieft | |
| `relief_vorhangfassade` | 0 | 0 | **1** | **1** | siehe 7.2 |

### Was bei 1:500 automatisch passiert (kein Code nötig, aber testen)
- 0.8-mm-Wand = 2 Voxel → Laibung (1) + Kern (1) → nur **aussen** vertieft (`fenster.laibungsseiten`).
- Öffnungen < 2 × Mindestwand (1.6 mm = 0.8 m real) werden nur gefüllt.
- Geschoss = 6 mm hoch; Aufteilung pro Geschoss bleibt.
- Entwurf ist gesperrt (eine 0.8-mm-Wand wäre nur 1 Voxel, keine Laibung möglich), das Modell ist ohnehin klein.

## 5. Klassenregeln pro Massstab

`b` behalten · `v` verdicken · `f` fuellen (Quader aus der Bounding Box) · `band` Brüstungsband (neu) · `–` entfernen · `F` Füller (Öffnungsmodus)

| IFC-Klasse | 1:500 | 1:200 | 1:100 | 1:50 | Kategorie |
|---|---|---|---|---|---|
| IfcWall, IfcWallStandardCase | b | b | b | b | Wand |
| IfcSlab | b | b | b | b | Decke |
| IfcRoof | b | b | b | b | Dach |
| IfcFooting | – | – | – | – | Fundament |
| IfcColumn | v | v | v | v | Stütze |
| IfcBeam | v | v | v | v | Träger |
| **IfcBeam.LINTEL** (neu) | f | f | f | v | Träger – Sturz, Storenkasten-Einlage: als Quader gedruckt, damit die Rinne der U-förmigen Einlage die Deckenunterseite nicht einkerbt; 1:50 behält das Detail |
| **IfcChimney** (neu) | v | v | v | v | Dach |
| IfcStair, IfcStairFlight | – | b | b | b | Treppe |
| **IfcRamp, IfcRampFlight** (neu) | – | b | b | b | Treppe |
| **IfcRailing** | – | **band** | **band** | **band** | Geländer |
| IfcCurtainWall | F | F | F | F (+Relief 1:100/1:50) | Verglasung |
| IfcPlate, IfcMember | – | – | – | – | Verglasung |
| IfcWindow, IfcDoor | F | F | F | F | Öffnung |
| IfcCovering | – | – | – | – | Ausbau |
| IfcCovering.CLADDING | b | b | b | b | Fassade |
| **IfcCovering.ROOFING** (neu) | – | – | b | b | Dach – *mit Testmodell prüfen, ob der Dachaufbau sauber im Paket landet* |
| IfcFurnishingElement | – | – | – | – | Möblierung |
| IfcFlowTerminal | – | – | – | – | Haustechnik |
| IfcBuildingElementProxy | – | – | – | – | Sonstiges |

Die Ganzes/Teil-Regel bleibt: Teile eines IfcRailing (IfcMember …) folgen der Regel `band` des Ganzen.

## 6. Datenmodell und Migration

Minimal-invasiv: die Spalte `regel.regelset` bleibt, enthält aber künftig genau die Massstab-Schlüssel
`"1:50" | "1:100" | "1:200" | "1:500"` (identisch mit den Schlüsseln von `config.MASSSTAEBE`).

```sql
CREATE TABLE IF NOT EXISTS massstab (
    regelset                  TEXT PRIMARY KEY,      -- "1:200"
    zahl                      INTEGER NOT NULL UNIQUE,  -- 200
    mindestdicke_wand_mm      REAL NOT NULL,
    mindestdicke_gelaender_mm REAL,                  -- NULL = kein band
    laibungstiefe_mm          REAL NOT NULL,
    mindestkern_laibung_mm    REAL NOT NULL,
    qualitaeten               TEXT NOT NULL,         -- "fein,entwurf,auto"
    qualitaet_default         TEXT NOT NULL,
    verbinder_erlaubt         INTEGER NOT NULL,
    fenster_default           TEXT NOT NULL,
    tuer_default              TEXT NOT NULL,
    relief_vorhangfassade     INTEGER NOT NULL DEFAULT 0
);
-- regel.aktion: CHECK um 'band' erweitern
```

- Neue Seed-Datei `db/seed/massstaebe.csv`. `db/seed/regeln.csv` neu mit vier Sets.
- **Migration** in `db.datenbank.Datenbank.__init__`:
  - `UPDATE regel SET regelset='1:200' WHERE regelset='Standard 1:200'`, analog `'Volumen 1:500'` → `'1:500'`.
    Gians eigene Änderungen bleiben damit erhalten. Unbekannte Sets werden verworfen, mit Log.
  - CHECK-Constraint: SQLite kann ihn nicht ändern → Tabelle `regel` neu anlegen, Daten kopieren, alte löschen.
  - Fehlende Klassen/Sets aus dem Seed ergänzen (`INSERT OR IGNORE`), bestehende Benutzerwerte nicht überschreiben.
- `exportlauf.regelset` bleibt und erhält "1:200".
- Neue Methoden: `massstab_parameter(regelset) -> dict`, `regeln_zuruecksetzen(regelset)`.
  `regelsets()` liefert die vier Stufen in fester Reihenfolge (500, 200, 100, 50).

## 7. Neue Funktionen

### 7.1 Aktion `band` – Geländer als Scheibe

Ein Geländer besteht aus Stäben (2 cm → 0.1 mm bei 1:200) und würde beim Voxelisieren verschwinden. `fuellen`
(Bounding Box) füllt bei L-förmigen Geländern den Balkon. Deshalb:

1. Alle Netze eines Geländers (das Ganze samt Teilen) werden **oberflächen-voxelisiert** auf das Raster des
   Hauptgitters (gleicher Ursprung und Pitch), d.h. jede Zelle, die das Netz berührt, zählt auch dann, wenn das
   Teil dünner als ein Voxel ist (Glasgeländer).
2. **Fussabdruck** = Projektion in den Grundriss (`any` über z).
3. **Verbreitern** auf `ceil(mindestdicke_gelaender_mm / pitch)` Voxel. Verbreitert wird zur Seite, auf der darunter
   Gebäude liegt (Balkon-/Deckenseite), damit das Band sicher aufsteht.
4. **Je Rasterspalte füllen**: vom obersten Gebäudevoxel darunter (Lücke ≤ 2 Voxel → schliessen) bis zum höchsten
   Geländervoxel. Damit funktionieren gerade, L-förmige, gebogene und geneigte (Treppe) Geländer gleich.
5. Liegt unter einer Spalte innerhalb von 2 Voxeln kein Gebäude (z.B. ein seitlich montiertes Geländer mit
   Abstand): Spalte weglassen. Fällt mehr als die Hälfte weg → ganzes Geländer weglassen und eine Warnung ausgeben.
6. Bänder werden nach der Voxelisierung **vor** den Öffnungen ins Gitter gesetzt, mit Geschoss des Geländers.
   Zuordnung zu Geschoss-/Dachteil wie bei den übrigen Bauteilen. Testfall: Geländer einer Dachterrasse.

Druckbarkeit/Oberfläche: Status für `band`-Bauteile nicht aus der IFC-Dicke berechnen (sonst immer «nicht
druckbar»), sondern Anzeige «Band 0.8 mm». Detailfeld (`ui/seite.py` ~Z. 890) entsprechend erweitern.

*Annahme:* Alle IfcRailing werden so behandelt, auch Treppengeländer (deren «Boden» ist die Treppe).
Sollen Treppengeländer weggelassen werden, reicht eine Ausnahme im Regelblatt (`IfcStair/IfcRailing → entfernen`).

### 7.2 Relief der Vorhangfassade (1:100, 1:50)

Ziel: Pfosten-/Riegelraster bzw. beliebige Feldformen sichtbar, **ohne Stützmaterial**.

Prinzip: **nichts steht vor, die Felder werden vertieft.** Die Fassade wird wie heute geschlossen (Füllkörper über
die Paketdicke). Danach wird jedes Feld (`IfcPlate` als Teil der `IfcCurtainWall`: Glas oder Paneel) **aussen um
`laibungstiefe_mm` ausgeräumt**. Pfosten und Riegel bleiben bündig mit der Fassadenfläche stehen.

Druckbarkeit: Senkrechte Pfosten laufen vom Schnitt (Geschossfuge) durchgehend nach oben, ohne Überhang. Die
Unterseite eines Riegels über einem vertieften Feld ist eine **Brücke zwischen zwei Pfosten** (wie der Sturz der
Fensterlaibung, die heute schon problemlos druckt), Tiefe ≤ Laibungstiefe. Über die Geschossfugen hinweg passt das
Raster automatisch, weil im fertigen Gitter abgezogen wird.

Regeln:
- Feldmaske = Voxel-Projektion der Platte auf die Fassadenebene (nicht die Bounding Box → beliebige Formen).
- Zwischen zwei Feldern muss ein Steg von ≥ 1 Voxel bleiben (sonst Maske um 1 Voxel erodieren). Felder unter
  2 × Mindestwand werden nicht vertieft.
- Restkern ≥ `mindestkern_laibung_mm` (wie Laibung). Ist er zu dünn, wird nicht vertieft.
- Gilt nur im Modus «vertieft» der Fenster. «ausgeschnitten» bleibt ausgeschnitten.
- Hat eine Vorhangfassade keine IfcPlate-Teile: Verhalten wie heute plus Hinweis.
- Bei 1:200 aus (Pfosten 5 cm = 0.25 mm < 1 Voxel), über den Parameter aber einschaltbar.
- Umsetzung als Erweiterung von `core/fenster.py` (Erweiterungspunkt `fuellkoerper` / neue Funktion
  `felder_vertiefen`). `ifc_modell.Fueller` braucht dafür die Platten-Teile der Vorhangfassade
  (neues Feld `felder: list[np.ndarray]`).
- Testmodell: `ARC_Modell_NEST_230328.ifc` (22 Vorhangfassaden, 58 Platten, 92 Members).

### 7.3 Qualität «auto» und Geschosswahl (v.a. 1:50)

- **auto**: Vor dem Anlegen des Gitters wird die Voxelzahl mit 0.4 mm berechnet. Überschreitet sie
  `gitter_grenze()` (oder 50 % davon, Wert in `config`), wird mit 0.8 mm gerechnet. Kennzahl/Bericht:
  «Qualität automatisch: entwurf (0.8 mm), weil …». Gilt für alle Massstäbe, Default nur bei 1:50.
- **Geschosswahl**: neue Einstellung (Mehrfachauswahl, Default alle). Nur Bauteile der gewählten Geschosse gehen
  ins Gitter → kleineres Gitter, Bauraumprüfung (`modell_uebersicht`) nur über die Auswahl.
- Raum-Ausschnitt (Clipbox aus IfcSpace) ist **nicht** Teil dieses Pakets, nur vormerken.

## 8. Oberfläche (02 Setup)

- Dropdown «Regelset» entfernen. **Massstab** als erstes Feld (Segmente 1:500 · 1:200 · 1:100 · 1:50).
- Massstab wechseln → Regeln + Parameter laden, Analyse neu (wie heute bei `massstab`):
  - Qualität auf `qualitaet_default` setzen, falls die aktuelle nicht erlaubt ist; nicht erlaubte Segmente deaktivieren.
  - Steckverbinder-Schalter bei `verbinder_erlaubt = 0` deaktivieren und ausschalten, mit Hinweis.
  - Fenster/Türen auf die Defaults setzen.
- Kurzer Hinweis je Massstab unter den Segmenten, z.B. *«1:500 – Wände min. 0.8 mm, Laibung nur aussen, keine
  Steckverbinder. Auskragungen brauchen Stützmaterial.»*
- Fester Hinweistext «0.4 mm Laibung» → dynamisch aus `laibungstiefe_mm`.
- Regelblatt zeigt die Regeln des aktuellen Massstabs. Änderungen werden pro Massstab gespeichert,
  dazu ein Knopf **«Auf Standard zurücksetzen»**.
- Bauraum-Meldung: statt «mind. 1:230» die nächste passende Stufe nennen; passt nicht einmal 1:500 →
  «Geschosse auswählen oder Modell teilen».
- `ui/zustand.py`: Feld `regelset` entfällt bzw. wird aus `massstab` abgeleitet; `ANALYSE_FELDER` anpassen.

## 9. Code-Struktur

- `core/regelwerk.py`: `@dataclass(frozen=True) class MassstabParameter` (Felder wie Tabelle 6, Defaults = heutige
  Werte aus `config`). `Regelwerk` erhält `massstab: str` und `parameter: MassstabParameter`.
  `Regelwerk.standard("1:200")` liest beide Seed-CSVs. `AKTIONEN`/`DRUCKEN` um `band` erweitern.
- `core/pipeline.py`: `analysieren()` und `erzeugen()` erhalten die Parameter über das Regelwerk.
  `_mindestdicke`, `_oeffnungen`, `paket_mindestdicke`, `oeffnungen.anwenden(... laibung_mm, kern_mm)` werden aus den
  Parametern gespeist.
- `config.py`: `MINDESTDICKE_WAND_MM`, `LAIBUNGSTIEFE_MM`, `MINDESTKERN_LAIBUNG_MM`, `FENSTER_DEFAULT`, `TUER_DEFAULT`
  entfernen (Defaults leben in `MassstabParameter`). `MASSSTAEBE` bleibt als einzige Liste der Stufen.
- Nebenbei: doppeltes `@lru_cache` über `regelwerk.alle_klassen` entfernen.

## 10. Arbeitspakete (Reihenfolge, je mit Abnahme)

Vor Beginn: `scripts/baseline_metriken.py` für alle Testmodelle bei 1:200 laufen lassen (Referenz).

| AP | Inhalt | Abnahme |
|---|---|---|
| 1 | Datenmodell, Seeds, Migration, `MassstabParameter`, `Regelwerk` | Tests: Migration alter DB (Benutzerregel bleibt), 4 Sets geladen, `band` erlaubt |
| 2 | Parameter durchreichen, `config` bereinigen | **1:200 ohne Geländer/Rampen-Änderung bitgleich zur Baseline**; Tests Wanddicke: 1:200 Wand 0.30 m → 1.6 mm, 0.10 m → 1.2 mm; 1:500 Wand 0.20 m → 0.8 mm, 0.50 m → 1.2 mm (gerundet); 1:500 nur Aussenlaibung |
| 3 | Oberfläche (Kap. 8) | Kein Regelset-Dropdown; Sperren/Defaults pro Massstab; Reset-Knopf; Test `test_oberflaeche` angepasst |
| 4 | Klassenregeln-Ergänzungen (Ramp, Chimney, ROOFING) | Alle 5 Testmodelle × 4 Massstäbe erzeugen ohne Fehler (1:50 mit Geschosswahl erst nach AP 6) |
| 5 | Aktion `band` | MFH_eBKPH_Real (8 Geländer) und NEST (13): Bänder durchgehend 0.8 mm, stehen auf der Decke, keine losen Teile; Warnung bei abgelösten Geländern |
| 6 | Qualität «auto» + Geschosswahl | 1:50 eines Geschosses von NEST läuft ohne Speicherabbruch; Bericht nennt die gewählte Voxelgrösse |
| 7 | Relief Vorhangfassade | NEST 1:100: Raster sichtbar, Feldtiefe = 0.8 mm, keine Überhänge > Laibungstiefe, Teile wasserdicht |

## 11. Offen / später
- Relief der Vorhangfassade (7.2, AP 7): umgesetzt, auf Wunsch wieder entfernt – folgt später.
  Erkenntnis: An schrägen Fassaden zerfällt ein 1 Voxel dicker Restkern (nur Kantenkontakt) in Streifen.
- Raum-Ausschnitt (IfcSpace-Clipbox) für 1:50.
- Sockel/Grundplatte für 1:500.
- Weitere Kategorien 1:100/1:50 (Sonnenschutz, freie Stahlbauteile, Möblierung) – bewusst zurückgestellt.
