"""Zentrale Defaultwerte für IFC2Print.

Zweck:   Fachkonstanten der Verarbeitung an einem Ort, jede mit Begründung.
Eingabe: keine (wird von core/, ui/ und scripts/ importiert)
Ausgabe: Konstanten und die Liste der Ausgabeziele (OUTPUT_TARGETS)

Druckerprofil und Material kommen im Betrieb aus der Datenbank (db/seed/*.csv);
die Werte hier sind Fallbacks. Massstabsabhängige Werte (Mindestdicke, Laibung, Öffnungs-Defaults)
stehen in db/seed/massstaebe.csv. «Festlegung» heisst: gewählter Wert, nicht gemessen.
Rein rechnerische Hilfsgrössen (Rundungstoleranzen, Blockgrössen gegen Speicherspitzen) stehen nicht hier,
sondern benannt und kommentiert im Modul, das sie braucht.
"""

from dataclasses import dataclass

# Druckerprofil (Prusa MK4, 0.4-mm-Düse) – Fallback, falls kein Profil übergeben wird
LAYER_HEIGHT_MM = 0.2
BUILD_VOLUME_X_MM = 250.0
BUILD_VOLUME_Y_MM = 210.0
BUILD_VOLUME_Z_MM = 220.0

# Druckbarkeit (Modellmass in mm): unter MIN_WALL_MM nicht druckbar,
# bis MIN_WALL_MM + CRITICAL_SPAN_MM druckbar, aber fragil («kritisch»).
MIN_WALL_MM = 0.8        # ≥ 2 Extrusionslinien à 0.4 mm
CRITICAL_SPAN_MM = 0.4   # eine weitere Extrusionslinie (0.4-mm-Düse)

# Georeferenzierte Modelle (core/ifc/model): Liegt ein Punkt im Grundriss weiter als so weit (real, mm)
# vom Ursprung, wird das Modell beim Einlesen zum Ursprung verschoben. STL/GLB speichern float32: bei
# LV95-Koordinaten (x ≈ 2.6·10⁹ mm, 1:200 → 1.3·10⁷ mm) wäre der kleinste Schritt 1 mm > 1 Voxel.
OFFSET_THRESHOLD_MM = 1_000_000.0
OFFSET_GRID_MM = 100_000.0   # Versatz in ganzen 100 m: Voxelraster bleibt bei allen Massstäben gleich

# Beispielmodell, das beim Öffnen der Seite erscheint (fehlt die Datei: ohne Beispiel)
START_MODEL = "testdaten/MFH_eBKPH_Real.ifc"

# Massstäbe, die die Oberfläche anbietet
SCALES = {"1:500": 500, "1:200": 200, "1:100": 100, "1:50": 50}   # = Regelsets (db/seed/massstaebe.csv)
SCALE_DEFAULT = "1:200"

# Voxel-Pitch (Kantenlänge eines Voxels im Modell, mm). Haupt-Laufzeithebel:
# der Aufwand wächst ~kubisch mit 1/Pitch. Muss ein Vielfaches der Layerhöhe sein,
# damit Geschoss-Fugen auf ganzen Layern liegen.
QUALITIES = {"fein": 0.4, "entwurf": 0.8}
QUALITY_DEFAULT = "fein"
# Qualität «auto»: fein, ausser das Gitter hätte bei 0.4 mm mehr als dieser Anteil von
# core/voxels/shell.grid_limit() Voxel – dann entwurf (0.8 mm, 8× weniger Voxel).
AUTO_GRID_RATIO = 0.5

# Hohlraum-Füllung (core/voxels/shell.py): Ein von EINEM Bauteil umschlossener Hohlraum
# wird gefüllt, wenn er in mindestens einer Achse höchstens so dick ist (real, mm).
# Deckt Wand-/Deckenkerne bis 0.75 m ab; Räume (kleinste Kante ≥ 1 m) bleiben hohl.
MAX_CAVITY_THICKNESS_MM = 750.0

# Speicherbremse (core/voxels/shell.check_grid): Die Erzeugung braucht gesamthaft rund BYTES_PER_VOXEL je
# Voxel (gemessen NEST «fein»: 107 Mio. Voxel, 3.4 GB). Erlaubt ist höchstens GRID_RAM_RATIO des
# Arbeitsspeichers, nie mehr als GRID_MAX_VOXELS (Rückfall, wenn das Betriebssystem den RAM nicht meldet).
BYTES_PER_VOXEL = 30
GRID_RAM_RATIO = 0.6
GRID_MAX_VOXELS = 400_000_000
# Ausreisser (core/analysis/surroundings.outlier): Bauteile, die weiter als OUTLIER_FACTOR × Gebäudegrösse
# (Kernbereich der Bauteilmitten, 10. bis 90. Perzentil, mindestens OUTLIER_MIN_M) davon entfernt
# liegen – z.B. ein verschobenes Bibliotheksobjekt –, werden nicht gedruckt (übersteuerbar).
OUTLIER_FACTOR = 3.0
OUTLIER_MIN_M = 20.0

# Mesh-Nachbearbeitung: Taubin-Glättung der Voxeltreppen und Quadric-Dezimierung.
# Taubin glättet ohne das Volumen schrumpfen zu lassen; mehr Durchgänge runden Kanten stärker ab (Festlegung).
SMOOTH_ITERATIONS = 4
DECIMATION_RATIO = 0.4       # Ziel-Anteil der Dreiecke (None = keine Dezimierung): ebene Voxelflächen
                             # bestehen aus vielen gleich ausgerichteten Dreiecken, die sich zusammenfassen lassen
DECIMATION_MAX_VOLUME_CHANGE = 0.02   # dezimiertes Netz nur übernehmen, wenn sich das Volumen höchstens um 2 %
                                      # ändert – sonst bleibt das volle Netz (Masshaltigkeit vor Dateigrösse)
VIEWER_MAX_FACES = 200_000   # Dreiecksbudget nur der Vorschau im Browser (Festlegung); die STL bleibt vollständig
# Lose Krumen (Modell-mm³): kleinere Stücke eines Teils, die nur über Kanten/Ecken hängen, und ebenso
# kleine eingeschlossene Hohlräume entfallen vor dem Vernetzen (core/parts/cleanup.without_sliver); nach dem
# Vernetzen ebenso kleine geschlossene Schalen (core/voxels/meshing.without_specks). 0.5 mm³ ≈ 8 Voxel bei 0.4 mm.
SPECK_MIN_VOLUME_MM3 = 0.5

# Druckbett (core/parts/print_layout.py), Modell-mm. Festlegung.
PRINT_GAP_MM = 8.0              # Abstand der Teile auf einem Druckbett
PRINT_BED_SPACING_MM = 100.0    # Abstand zweier Druckbetten in der Datei mit allen Teilen (trennt sie sichtbar)

# Überhänge (core/parts/overhangs.py), Modell-mm. FDM überbrückt waagrechte Strecken bis etwa 10 mm sauber,
# wenn sie beidseitig aufliegen (PLA/PETG mit Lüfter); längere Brücken hängen durch und brauchen Stützen.
BRIDGE_MAX_MM = 10.0
# Kleinere Stützflächen je Teil werden nicht gemeldet (einzelne Voxel an Kanten, Stützenköpfe). 25 mm² = 5 × 5 mm.
OVERHANG_MIN_MM2 = 25.0
# Liegt mindestens dieser Anteil der Stützfläche über dem Modell statt über dem Bett, lautet der Vorschlag
# «anders zuordnen»: Stützen in den Räumen eines Massstabsmodells lassen sich kaum entfernen.
OVERHANG_ON_MODEL_RATIO = 0.5

# Mindestdicke der Wände, Laibungstiefe, Restkern, Öffnungs-Defaults, erlaubte Qualitäten und
# Steckverbinder hängen vom Massstab ab: core.analysis.ruleset.ScaleParameters (db/seed/massstaebe.csv).
ROOF_ZONE_MIN_HEIGHT_MM = 1000   # Dachschale mindestens so hoch (real): Träger darin zählen zum Dach

# Geschossteile (core/parts/), reale mm: Die Fuge zwischen zwei Geschossen bleibt eben.
# Absätze bis JOINT_LEVELING_MM unter der Fuge (Dämmung, Bekleidung unter einer Decke) werden
# abgeschnitten, Rücksprünge bis dahin über der Fuge aufgefüllt. Ein Vollabschnitt bis
# JOINT_SLAB_MM gilt als Decke (darüber: Wand); tiefer liegende Deckenbereiche, die breiter als
# JOINT_WIDTH_MM sind (z.B. TG-Dach neben dem Haus), gehen ganz ans untere Teil statt zerschnitten.
JOINT_LEVELING_MM = 150.0
JOINT_SLAB_MM = 1000.0
JOINT_WIDTH_MM = 2000.0
# Tiefer als die Unterseite des Teils ragende Stücke (letzte Treppenstufen in der Deckenöffnung) gehen bis zu dieser
# Tiefe (real) ans Teil darunter, sonst hingen sie unter der Bodenplatte und höben das Teil vom Bett ab.
JOINT_OVERHANG_MM = 500.0
# Suchfenster um die Geschoss-Z (reale m), in dem die Deckenunterkante gesucht wird: nach unten
# tief genug für dicke, geebnete Bodenplatten samt Magerbeton, nach oben nur knapp.
JOINT_SEARCH_WINDOW_BELOW_M = 1.2
JOINT_SEARCH_WINDOW_ABOVE_M = 0.2
# Mindest-Anstieg der Voxelzahl (Anteil der Grundfläche), damit eine Schicht als Deckenunterkante
# gilt. Sonst: Schnitt auf Geschoss-Z + Warnung.
JOINT_MIN_RISE = 0.05
# Dächer werden eigene Teile, sofern sie mindestens diesen Anteil am Volumen haben; Inseln
# (abgetrennte Stücke eines Teils, kleiner als ISLAND_RATIO des Hauptstücks) gehen ans Nachbarteil.
ROOF_MIN_RATIO = 0.02
ISLAND_RATIO = 0.25
# Lose Splitter: Stücke unter dieser Voxelzahl ohne jeden Kontakt zu einem Teil werden gelöscht.
SLIVER_MAX_VOXELS = 64
# Ganze Teile unter diesem Anteil am Gesamtvolumen gehen ans Nachbarteil mit der grössten Kontaktfläche.
SMALL_PART_RATIO = 0.01
# Dachschale (core/parts/roof.roof_part): Dachbauteile sind Dach, wenn sie steiler als ROOF_INCLINATION_DEG
# geneigt sind oder (flach) mehr als ROOF_ABOVE_ELEVATION_MM (real) über der Kote ihres Geschosses liegen.
ROOF_INCLINATION_DEG = 5.0
ROOF_ABOVE_ELEVATION_MM = 1500.0
# Gefälle (core/packages/plates.has_slope): Decken, deren Oberseite überwiegend so flach geneigt ist,
# werden im Voxelgitter eben gemacht (tiefste bis höchste Stelle gefüllt).
SLOPE_DEG = (0.3, 5.0)
SLOPE_MIN_AREA_RATIO = 0.5      # «überwiegend»: mindestens die Hälfte der Oberseite liegt in SLOPE_DEG
TOP_MIN_NORMAL_Z = 0.5          # als Oberseite zählen Flächen, die höchstens 60° geneigt sind (cos 60° = 0.5)

# Platten und Wandpakete (core/packages/)
PLATE_MAX_THICKNESS_RATIO = 0.5  # plattenartig: Dicke höchstens die Hälfte der zweitkleinsten Kante
PLATE_AXIS_SNAP_DEG = 0.5       # Plattenrichtungen bis so nahe an x/y/z werden auf die Achse eingerastet
                                # (Modellierungsungenauigkeit, sonst entstehen schräge Voxeltreppen)
WALL_MAX_NORMAL_Z = 0.5         # Wand: Normale höchstens 30° aus der Waagrechten (Platte steiler als 60°)
PACKAGE_PARALLEL_DEG = 2.0      # Platten bilden nur ein Paket, wenn ihre Normalen höchstens so weit abweichen
PACKAGE_COVERED_RATIO = 0.9     # Glied gilt als abgedeckt (nicht freistehend), wenn so viel seiner Fläche an
                                # anderen Gliedern liegt; freistehende Glieder brauchen selbst die Mindestdicke
PACKAGE_GAP_MIN_MM = 10.0       # Spalt zwischen Schichten (real), der immer zum Paket zählt – auch wo die halbe
                                # Mindestwand kleiner wäre (sehr grosse Massstäbe). Festlegung.

# «Umgebung»: Bauteile, deren Name, Typname oder Layer (z.B. ArchiCAD-Ebene «011 Stützwände»)
# eines dieser Stichworte enthält (klein geschrieben), werden nicht gedruckt – Stützmauern
# u.ä. sind oft als normale IfcWall modelliert. Je Bauteil in der Oberfläche übersteuerbar.
SURROUNDINGS_KEYWORDS = ("stützmauer", "stuetzmauer", "stützwand", "stuetzwand", "stützwänd", "stuetzwaend",
                         "umgebung", "gelände", "gelaende", "aussenanlage", "außenanlage", "terrain",
                         "retaining", "topograph", "landscap")   # «außenanlage»: Schreibweise aus deutschen IFC
# Gesucht wird am Wortanfang («stützwänd» trifft «Stützwände»). Diese Wörter zählen nie – sie beginnen
# zwar mit einem Stichwort, sind aber Gebäudeteile.
SURROUNDINGS_EXCEPTIONS = ("geländer", "gelaender")
# Klassen, die immer Umgebung sind (Gelände, Tiefbau)
SURROUNDINGS_CLASSES = ("IfcGeographicElement", "IfcCivilElement")

# Fenster-/Türfüller (core/openings/detection.find_hosts): Ein Füller gilt als parallel zur Ebene des Pakets,
# wenn seine Normale um höchstens HOST_PARALLEL_DEG abweicht. In einer Wand muss der Teil des Füllers
# mindestens diese Anteile seiner Breite bzw. Höhe abdecken – sonst ist die Wand kein Wirt (Leibung
# an einer Querwand, Gaubenwange).
HOST_PARALLEL_DEG = 10.0
HOST_MIN_WIDTH_RATIO = 0.2
HOST_MIN_HEIGHT_RATIO = 0.5
# Öffnungen werden nur ausgeschnitten oder vertieft, wenn sie mindestens so viele Mindestwände breit und hoch
# sind – schmalere Schlitze liessen sich nicht sauber drucken und bleiben geschlossen.
OPENING_MIN_WALLS = 2.0

# Geländer als Band (core/voxels/band.py)
RAILING_GAP_VOXELS = 2          # so grosse Lücken zwischen Gebäude und Geländerunterkante werden geschlossen
RAILING_MAX_LOST_RATIO = 0.5    # Geländer entfällt, wenn mehr als die Hälfte seiner Spalten keine Auflage hat

# Kalkulation (Schätzung, Festlegung – nicht mit Slicer-Werten abgeglichen)
VOLUME_FACTOR = 0.4        # Anteil des Hüllvolumens, der real als Filament anfällt (Wände + Infill)
THROUGHPUT_CM3_H = 10.0    # effektiver Volumendurchsatz des Druckers
LAYER_CHANGE_H = 0.001     # Zeitzuschlag je Layer (= 3.6 s: Fahrwege, Z-Hub)

# Steckverbinder (core/connectors/planning.py), Modell-mm. Nur dort, wo das untere Teil die Decke darüber trägt
# (Wandkronen, Stützenköpfe): Zapfen als Kegelstumpf auf der Krone, Tasche in der Deckenunterseite.
# Das obere Teil wird nur aufgelegt (kein Einrasten). Rechteckig auf länglichen Kontaktflächen
# (Wände), rund auf gedrungenen (Stützen, Ecken). Masse gelten an der Kontaktfläche.
CLEARANCE_MM = 0.20             # Luft zwischen Zapfen und Tasche, ringsum und oben. Fallback: im Betrieb gilt
                                # clearance_mm des Druckerprofils (db/seed/profile.csv, ebenfalls 0.20 mm)
PEG_ROUND_DIAMETER_MM = (3.0, 2.4, 2.0, 1.6, 1.2)   # grösster passender Durchmesser gewinnt; min. 1.2
PEG_RECT_WIDTH_MM = (2.0, 1.6, 1.2)  # Breite quer zur Wand; Länge = 2 × Breite (min. 1.2 × 2.4)
PEG_TAPER_DEG = 15.0            # Flankenneigung gegen die Senkrechte: oben schmaler, leicht aufzusetzen
PEG_DEPTH_RATIO = 0.6           # Zapfenhöhe = Anteil der Deckendicke über dem Zapfen (Tasche bleibt Sackloch)
PEG_MAX_ENGAGEMENT_MM = 3.0     # Obergrenze der Zapfenhöhe, auch bei dicken Decken (Festlegung)
MIN_ENGAGEMENT_MM = 0.5         # kürzerer Zapfen führt nicht → kein Verbinder an dieser Stelle
ELONGATION_RATIO = 2.0          # Kontaktfläche (lokal) mindestens so lang wie breit × ELONGATION_RATIO → Rechteck
OVERLAP_MM = 0.4                # Zapfen taucht in die Wand ein (vermeidet koplanare Flächen beim Boolean)
CYLINDER_SEGMENTS = 48          # Kreis als 48-Eck: bei 3 mm Durchmesser weicht die Sehne höchstens
                                # 0.003 mm vom Kreis ab, weit unter der Druckgenauigkeit
CONNECTORS_PER_JOINT = 3        # drei Punkte: das obere Teil liegt statisch bestimmt auf
CONNECTOR_MIN_SPACING_MM = 10.0  # Mindestabstand zweier Verbinder derselben Fuge: die Punkte verteilen sich
CONTACT_MIN_COLUMNS = 40        # kleinere vertikale Berührungen zweier Teile (Anzahl Voxelsäulen, bei 0.4 mm
                                # Pitch 6.4 mm²) bekommen keine Verbinder
CONTACT_MIN_PLANE_RATIO = 0.2   # Kontaktebenen unter 20 % der grössten Ebene zweier Teile (Absätze, Podeste)
                                # bekommen keine Verbinder
CONTACT_SHAPE_RADIUS_MM = 3.0   # Umkreis, in dem die Form der Kontaktfläche bestimmt wird (länglich → Rechteck)
CONNECTOR_MAX_VOLUME_CHANGE = 0.2  # Boolean-Ergebnis verwerfen (Teil bleibt ohne Verbinder), wenn sich das Volumen
                                   # um mehr als 20 % ändert – Schutz vor fehlerhaften Booleans


# Ausgabeziele (untere Leiste): nur FDM ist umgesetzt, die übrigen sind als «bald» angelegt.
# Ein neues Verfahren = ein Eintrag hier + eine Exportfunktion in core/.
@dataclass(frozen=True)
class OutputTarget:
    key: str                      # "fdm", "resin", "laser", "3mf", "shell", "web"
    name: str                     # "FDM"
    format: str                   # "STL"
    modes: tuple[str, ...]        # Ansichtsmodi rechts
    field_names: tuple[str, ...]  # Setup-Felder in 02
    exports: tuple[str, ...]      # Downloads in der unteren Leiste
    available: bool               # False = «bald»
    description_text: str         # Tooltip


_FDM_FIELDS = ("scale", "profile", "material", "selected_storeys", "quality", "windows", "doors", "align",
               "connectors")
OUTPUT_TARGETS = (
    OutputTarget("fdm", "FDM", "STL", ("ifc", "status", "stl"), _FDM_FIELDS, ("stl", "zip", "plate"),
                True, "Filamentdruck: wasserdichtes Volumenmodell, ganz oder je Geschoss"),
    OutputTarget("resin", "Resin", "STL hohl", ("ifc", "status", "stl"), (), (), False,
                "Hohl mit Drainage, feinere Details ab 1:500"),
    OutputTarget("laser", "Lasercut", "SVG/DXF", ("ifc", "layers", "boegen"), (), (), False,
                "Gitter schichtweise als Schnittbögen"),
    OutputTarget("3mf", "3MF Farbe", "je Geschoss", ("ifc", "color"), (), (), False,
                "Mehrfarbig, eine Farbe je Geschoss"),
    OutputTarget("shell", "Hülle", "Analyse", ("ifc", "shell", "comparison"), (), (), False,
                "Dichte vereinfachte Hülle für Wind-/Schatten-/Kontextstudien"),
    OutputTarget("web", "Web/AR", "GLB", ("ifc", "explosion"), (), (), False,
                "GLB/USDZ, Explosionsmodell, taktile Variante"),
)
OUTPUT_TARGET_DEFAULT = "fdm"
