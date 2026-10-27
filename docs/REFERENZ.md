# Referenz – Stellgrössen und Regeln

Automatisch erzeugt mit `python scripts/reference.py` aus [config.py](../config.py), [core/analysis/ruleset.py](../core/analysis/ruleset.py) und [db/seed/](../db/seed/). Nicht von Hand ändern: `tests/test_docs.py` schlägt fehl, sobald die Datei nicht mehr zum Code passt. Was die Verfahren tun, erklärt das [README](../README.md); hier steht, mit welchen Werten und warum.

## Inhalt

- [Parameter je Massstab](#parameter-je-massstab)
- [Klassenregeln](#klassenregeln)
- [Druckerprofil und Druckbarkeit](#druckerprofil-und-druckbarkeit)
- [Import](#import)
- [Massstäbe und Qualität](#massstäbe-und-qualität)
- [Voxelgitter und Netz](#voxelgitter-und-netz)
- [Umgebung und Ausreisser](#umgebung-und-ausreisser)
- [Platten und Pakete](#platten-und-pakete)
- [Öffnungen](#öffnungen)
- [Geländer als Band](#geländer-als-band)
- [Geschoss-, Dach- und Deckenteile](#geschoss--dach--und-deckenteile)
- [Druckbett und Überhänge](#druckbett-und-überhänge)
- [Steckverbinder](#steckverbinder)
- [Kalkulation](#kalkulation)
- [Oberfläche und Ausgabe](#oberfläche-und-ausgabe)

## Parameter je Massstab

Code: [core/analysis/ruleset.py](../core/analysis/ruleset.py) (`ScaleParameters`) · Werte und Begründungen: [db/seed/massstaebe.csv](../db/seed/massstaebe.csv)

Was neben den Klassenregeln vom Massstab abhängt (Modellmass, mm). Defaults = 1:200. Das Druckerprofil bleibt die physikalische Grenze, der Massstab die gestalterische: Decken, Dächer und Stützen richten sich nach der Mindestwand des Profils, Wände nach ``min_thickness_wall_mm``.

| Parameter | 1:500 | 1:200 | 1:100 | 1:50 | Erklärung |
|---|---|---|---|---|---|
| `min_thickness_wall_mm` | 0.8 | 1.2 | 1.2 | 1.2 | Wände (senkrechte Pakete); wirksam max(Profil, dieser Wert). 0.8 mm = 2 Extrusionslinien, 1.2 mm = 3. Dickere Wände behalten ihre skalierte Dicke, gerundet auf ganze Voxel ([core/packages/scaling.py](../core/packages/scaling.py)). |
| `min_thickness_railing_mm` | – | 0.8 | 0.8 | 0.8 | Aktion «band»; None = keine Bänder |
| `reveal_depth_mm` | 0.4 | 0.4 | 0.8 | 1.6 | Tiefe vertiefter Öffnungen, real rund 8 cm; wird reduziert, wenn der Kern sonst zu dünn wäre |
| `min_core_reveal_mm` | 0.8 | 0.8 | 0.8 | 0.8 | Wandkern, der hinter einer Laibung mindestens stehen bleibt; wirksam max(Profil, dieser Wert). 0.8 mm = 2 Extrusionslinien: Ein Kern aus einer einzigen Linie (0.4 mm) war im Testdruck zu dünn. |
| `qualities` | fein | fein, entwurf, auto | fein, entwurf, auto | fein, entwurf, auto | wählbare Qualitäten (02 Setup), die übrigen gesperrt |
| `quality_default` | fein | fein | fein | auto | Qualität nach dem Wechsel, falls die bisherige nicht erlaubt ist |
| `connectors_allowed` | nein | ja | ja | ja | Steckverbinder zwischen den Geschossteilen möglich |
| `window_default` | geschlossen | vertieft | vertieft | vertieft | Öffnungsmodus nach dem Wechsel: geschlossen, vertieft, ausgeschnitten |
| `door_default` | geschlossen | vertieft | vertieft | vertieft |  |

- **1:500:** Volumenmodell: Gebäudeform und Geschosse ohne Treppen und Geländer. Fenster und Türen geschlossen, weil eine Wand bloss zwei Voxel dick ist: Eine Laibung liesse keinen Kern von zwei Extrusionslinien stehen. Nur «fein», weil eine Wand mit «entwurf» bloss ein Voxel dick wäre und keine Laibung zuliesse. Keine Steckverbinder: Die Zapfen passen nicht in die dünnen Wände. Auskragungen brauchen Stützmaterial.
- **1:200:** Standard: Treppen, Geländer als Band, Fenster vertieft – in Wänden von 1.2 mm nur aussen, damit hinter der Laibung ein Kern von 0.8 mm (zwei Extrusionslinien) bleibt.
- **1:100:** Detail: tiefere Laibungen, der Dachaufbau wird sichtbar.
- **1:50:** Ausschnitt: einzelne Geschosse wählen. Qualität «auto», weil das ganze Gebäude mit 0.4-mm-Voxeln schnell zu gross für den Arbeitsspeicher wird.

## Klassenregeln

Code: [core/analysis/ruleset.py](../core/analysis/ruleset.py) (`Ruleset`) · Werte und Begründungen: [db/seed/regeln.csv](../db/seed/regeln.csv) · Aktionen, Vererbung und Aggregate: [README › Regeln](../README.md#regeln)

Standard je Massstab; eigene Regeln speichert die Datenbank. – = keine eigene Regel, es gilt die Regel der Oberklasse. In regeln.csv steht jede Regel einmal für «alle» Massstäbe, dazu nur die Abweichungen einzelner Massstäbe.

| Regel | Kategorie | 1:500 | 1:200 | 1:100 | 1:50 | Begründung |
|---|---|---|---|---|---|---|
| `IfcWall` | Wand | behalten | behalten | behalten | behalten | **1:500:** Auch im Volumenmodell bleiben die Innenwände: Sie tragen die Decke darüber, Stützmaterial im Gebäude liesse sich nicht entfernen. Dünnere Wände werden auf die Mindestdicke gebracht.<br>**1:200, 1:100, 1:50:** Wände geben die Gebäudeform und tragen die Decke darüber. Sie behalten ihre Dicke; nur dünnere werden als Paket auf die Mindestdicke des Massstabs gebracht. |
| `IfcWallStandardCase` | Wand | behalten | behalten | behalten | behalten | Wie IfcWall. |
| `IfcSlab` | Decke | behalten | behalten | behalten | behalten | Decken bilden Boden und Deckel der Geschossteile. Zu dünne Decken werden als Paket auf die Mindestwand des Druckerprofils gebracht. |
| `IfcRoof` | Dach | behalten | behalten | behalten | behalten | Das Dach prägt die Gebäudeform. Dachflächen und Sparren darin folgen dieser Regel, egal wie das Autorentool das Dach zerlegt. |
| `IfcFooting` | Fundament | entfernen | entfernen | entfernen | entfernen | Fundamente liegen im Erdreich und sind am Modell nicht sichtbar; die Unterseite des untersten Geschosses bleibt so eben. |
| `IfcColumn` | Stütze | verdicken | verdicken | verdicken | verdicken | Stützen tragen die Decke darüber. Sind sie dünner als die Mindestwand, werden sie allseitig aufgedickt, statt wegzufallen. |
| `IfcBeam` | Träger | verdicken | verdicken | verdicken | verdicken | Träger tragen und sind oft schlank. Sind sie dünner als die Mindestwand, werden sie allseitig aufgedickt. |
| `IfcBeam.LINTEL` | Träger | fuellen | fuellen | fuellen | – | Sturz und Storenkasten-Einlage als Quader: Die Rinne der U-förmigen Einlage würde sonst die Deckenunterseite einkerben. Bei 1:50 gilt die Regel von IfcBeam, das Detail bleibt. |
| `IfcChimney` | Dach | verdicken | verdicken | verdicken | verdicken | Kamine prägen die Dachsilhouette. Schlanke Kamine werden auf die Mindestwand aufgedickt. |
| `IfcStair` | Treppe | entfernen | behalten | behalten | behalten | **1:500:** Im Volumenmodell zu fein: Eine Stufe (17 cm) wäre bei 1:500 dünner als ein Voxel.<br>**1:200, 1:100, 1:50:** Treppen zeigen die Erschliessung. Ab 1:200 ist eine Stufe rund zwei Voxel hoch und druckbar. |
| `IfcStairFlight` | Treppe | entfernen | behalten | behalten | behalten | **1:500:** Im Volumenmodell zu fein: Eine Stufe (17 cm) wäre bei 1:500 dünner als ein Voxel.<br>**1:200, 1:100, 1:50:** Treppenlauf, wie IfcStair. |
| `IfcRamp` | Treppe | entfernen | behalten | behalten | behalten | **1:500:** Im Volumenmodell zu fein, wie Treppen.<br>**1:200, 1:100, 1:50:** Rampen zeigen die Erschliessung, wie Treppen. |
| `IfcRampFlight` | Treppe | entfernen | behalten | behalten | behalten | **1:500:** Im Volumenmodell zu fein, wie Treppen.<br>**1:200, 1:100, 1:50:** Rampenlauf, wie IfcRamp. |
| `IfcRailing` | Geländer | entfernen | band | band | band | **1:500:** Im Volumenmodell zu filigran; bei 1:500 gibt es keine Bänder.<br>**1:200, 1:100, 1:50:** Geländerstäbe (2 cm) würden beim Voxelisieren verschwinden. Das Geländer wird deshalb als dünne Scheibe vom Boden bis zur Geländerhöhe gedruckt. |
| `IfcCurtainWall` | Verglasung | entfernen | entfernen | entfernen | entfernen | Die Vorhangfassade selbst wird nicht gedruckt. Ihre Öffnung schliesst ein Füller nach dem Öffnungsmodus der Fenster (voll, vertieft oder offen). |
| `IfcPlate` | Verglasung | entfernen | entfernen | entfernen | entfernen | Meist Glas von Vorhangfassaden, zu dünn für den Druck; die Fläche schliesst der Füller der Fassade. Als Teil eines Dachs gilt dessen Regel. |
| `IfcMember` | Verglasung | entfernen | entfernen | entfernen | entfernen | Meist Pfosten und Riegel von Vorhangfassaden, zu dünn für den Druck. Als Teil eines Dachs oder Geländers gilt dessen Regel. |
| `IfcWindow` | Öffnung | entfernen | entfernen | entfernen | entfernen | Fenster werden nicht als Bauteil gedruckt. Die Öffnung in der Wand wird nach dem Öffnungsmodus geschlossen, vertieft oder ausgeschnitten. |
| `IfcDoor` | Öffnung | entfernen | entfernen | entfernen | entfernen | Türen werden nicht als Bauteil gedruckt. Die Öffnung in der Wand wird nach dem Öffnungsmodus geschlossen, vertieft oder ausgeschnitten. |
| `IfcCovering` | Ausbau | entfernen | entfernen | entfernen | entfernen | Bodenbeläge, Deckenverkleidungen und Dämmungen im Innern sind dünn und am Modell nicht sichtbar. |
| `IfcCovering.CLADDING` | Fassade | behalten | behalten | behalten | behalten | Die Fassadenbekleidung bildet die Aussenhaut und bestimmt die Gebäudemasse; sie wird mit der Wand zum Paket zusammengefasst. |
| `IfcCovering.ROOFING` | Dach | entfernen | entfernen | behalten | behalten | **1:500, 1:200:** Der Dachaufbau ändert die Dachform bei 1:500 und 1:200 kaum.<br>**1:100, 1:50:** Ab 1:100 trägt der Dachaufbau sichtbar zur Dachdicke bei; er wird mit dem Dach zum Paket zusammengefasst. |
| `IfcFurnishingElement` | Möblierung | entfernen | entfernen | entfernen | entfernen | Möbel gehören nicht ins Massstabsmodell. |
| `IfcFlowTerminal` | Haustechnik | entfernen | entfernen | entfernen | entfernen | Haustechnik (Sanitärapparate, Leuchten) gehört nicht ins Massstabsmodell. |
| `IfcBuildingElementProxy` | Sonstiges | entfernen | entfernen | entfernen | entfernen | Proxies sind unbestimmt, oft Bibliotheksobjekte. Bei Bedarf je Bauteil drucken oder eine eigene Regel anlegen. |

## Druckerprofil und Druckbarkeit

Code: [core/analysis/printability.py](../core/analysis/printability.py)

Druckerprofil (Prusa MK4, 0.4-mm-Düse) – Fallback, falls kein Profil übergeben wird

| Konstante | Wert | Erklärung |
|---|---|---|
| `LAYER_HEIGHT_MM` | `0.2` |  |
| `BUILD_VOLUME_X_MM` | `250.0` |  |
| `BUILD_VOLUME_Y_MM` | `210.0` |  |
| `BUILD_VOLUME_Z_MM` | `220.0` |  |

Druckbarkeit (Modellmass in mm): unter `MIN_WALL_MM` nicht druckbar, bis `MIN_WALL_MM` + `CRITICAL_SPAN_MM` druckbar, aber fragil («kritisch»).

| Konstante | Wert | Erklärung |
|---|---|---|
| `MIN_WALL_MM` | `0.8` | ≥ 2 Extrusionslinien à 0.4 mm |
| `CRITICAL_SPAN_MM` | `0.4` | eine weitere Extrusionslinie (0.4-mm-Düse) |

## Import

Code: [core/ifc/model.py](../core/ifc/model.py)

| Konstante | Wert | Erklärung |
|---|---|---|
| `OFFSET_THRESHOLD_MM` | `1_000_000.0` | Georeferenzierte Modelle ([core/ifc/model](../core/ifc/model.py)): Liegt ein Punkt im Grundriss weiter als so weit (real, mm) vom Ursprung, wird das Modell beim Einlesen zum Ursprung verschoben. STL/GLB speichern float32: bei LV95-Koordinaten (x ≈ 2.6·10⁹ mm, 1:200 → 1.3·10⁷ mm) wäre der kleinste Schritt 1 mm > 1 Voxel. |
| `OFFSET_GRID_MM` | `100_000.0` | Versatz in ganzen 100 m: Voxelraster bleibt bei allen Massstäben gleich |

## Massstäbe und Qualität

Massstäbe, die die Oberfläche anbietet

| Konstante | Wert | Erklärung |
|---|---|---|
| `SCALES` | `{"1:500": 500, "1:200": 200, "1:100": 100, "1:50": 50}` | = Regelsets ([db/seed/massstaebe.csv](../db/seed/massstaebe.csv)) |
| `SCALE_DEFAULT` | `"1:200"` |  |

Mindestdicke der Wände, Laibungstiefe, Restkern, Öffnungs-Defaults, erlaubte Qualitäten und Steckverbinder hängen vom Massstab ab: core.analysis.ruleset.ScaleParameters ([db/seed/massstaebe.csv](../db/seed/massstaebe.csv)).

Voxel-Pitch (Kantenlänge eines Voxels im Modell, mm). Haupt-Laufzeithebel: der Aufwand wächst ~kubisch mit 1/Pitch. Muss ein Vielfaches der Layerhöhe sein, damit Geschoss-Fugen auf ganzen Layern liegen.

| Konstante | Wert | Erklärung |
|---|---|---|
| `QUALITIES` | `{"fein": 0.4, "entwurf": 0.8}` |  |
| `QUALITY_DEFAULT` | `"fein"` |  |
| `AUTO_GRID_RATIO` | `0.5` | Qualität «auto»: fein, ausser das Gitter hätte bei 0.4 mm mehr als dieser Anteil von [core/voxels/shell.grid_limit](../core/voxels/shell.py)() Voxel – dann entwurf (0.8 mm, 8× weniger Voxel). |

## Voxelgitter und Netz

Code: [core/voxels/](../core/voxels/)

| Konstante | Wert | Erklärung |
|---|---|---|
| `MAX_CAVITY_THICKNESS_MM` | `750.0` | Hohlraum-Füllung ([core/voxels/shell.py](../core/voxels/shell.py)): Ein von EINEM Bauteil umschlossener Hohlraum wird gefüllt, wenn er in mindestens einer Achse höchstens so dick ist (real, mm). Deckt Wand-/Deckenkerne bis 0.75 m ab; Räume (kleinste Kante ≥ 1 m) bleiben hohl. |

Speicherbremse ([core/voxels/shell.check_grid](../core/voxels/shell.py)): Die Erzeugung braucht gesamthaft rund `BYTES_PER_VOXEL` je Voxel (gemessen NEST «fein»: 107 Mio. Voxel, 3.4 GB). Erlaubt ist höchstens `GRID_RAM_RATIO` des Arbeitsspeichers, nie mehr als `GRID_MAX_VOXELS` (Rückfall, wenn das Betriebssystem den RAM nicht meldet).

| Konstante | Wert | Erklärung |
|---|---|---|
| `BYTES_PER_VOXEL` | `30` |  |
| `GRID_RAM_RATIO` | `0.6` |  |
| `GRID_MAX_VOXELS` | `400_000_000` |  |
| `SMOOTH_ITERATIONS` | `4` | Mesh-Nachbearbeitung: Taubin-Glättung der Voxeltreppen und Quadric-Dezimierung. Taubin glättet ohne das Volumen schrumpfen zu lassen; mehr Durchgänge runden Kanten stärker ab (Festlegung). |
| `DECIMATION_RATIO` | `0.4` | Ziel-Anteil der Dreiecke (None = keine Dezimierung): ebene Voxelflächen bestehen aus vielen gleich ausgerichteten Dreiecken, die sich zusammenfassen lassen |
| `DECIMATION_MAX_VOLUME_CHANGE` | `0.02` | dezimiertes Netz nur übernehmen, wenn sich das Volumen höchstens um 2 % ändert – sonst bleibt das volle Netz (Masshaltigkeit vor Dateigrösse) |
| `SPECK_MIN_VOLUME_MM3` | `0.5` | Lose Krumen (Modell-mm³): kleinere Stücke eines Teils, die nur über Kanten/Ecken hängen, und ebenso kleine eingeschlossene Hohlräume entfallen vor dem Vernetzen ([core/parts/cleanup.without_sliver](../core/parts/cleanup.py)); nach dem Vernetzen ebenso kleine geschlossene Schalen ([core/voxels/meshing.without_specks](../core/voxels/meshing.py)). 0.5 mm³ ≈ 8 Voxel bei 0.4 mm. |

## Umgebung und Ausreisser

Code: [core/analysis/surroundings.py](../core/analysis/surroundings.py)

«Umgebung»: Bauteile, deren Name, Typname oder Layer (z.B. ArchiCAD-Ebene «011 Stützwände») eines dieser Stichworte enthält (klein geschrieben), werden nicht gedruckt – Stützmauern u.ä. sind oft als normale IfcWall modelliert. Je Bauteil in der Oberfläche übersteuerbar.

| Konstante | Wert | Erklärung |
|---|---|---|
| `SURROUNDINGS_KEYWORDS` | `("stützmauer", "stuetzmauer", "stützwand", "stuetzwand", "stützwänd", "stuetzwaend", "umgebung", "gelände", "gelaende", "aussenanlage", "außenanlage", "terrain", "retaining", "topograph", "landscap")` | «außenanlage»: Schreibweise aus deutschen IFC |
| `SURROUNDINGS_EXCEPTIONS` | `("geländer", "gelaender")` | Gesucht wird am Wortanfang («stützwänd» trifft «Stützwände»). Diese Wörter zählen nie – sie beginnen zwar mit einem Stichwort, sind aber Gebäudeteile. |
| `SURROUNDINGS_CLASSES` | `("IfcGeographicElement", "IfcCivilElement")` | Klassen, die immer Umgebung sind (Gelände, Tiefbau) |

Ausreisser ([core/analysis/surroundings.outlier](../core/analysis/surroundings.py)): Bauteile, die weiter als `OUTLIER_FACTOR` × Gebäudegrösse (Kernbereich der Bauteilmitten, 10. bis 90. Perzentil, mindestens `OUTLIER_MIN_M`) davon entfernt liegen – z.B. ein verschobenes Bibliotheksobjekt –, werden nicht gedruckt (übersteuerbar).

| Konstante | Wert | Erklärung |
|---|---|---|
| `OUTLIER_FACTOR` | `3.0` |  |
| `OUTLIER_MIN_M` | `20.0` |  |

## Platten und Pakete

Code: [core/packages/](../core/packages/)

| Konstante | Wert | Erklärung |
|---|---|---|
| `SLOPE_DEG` | `(0.3, 5.0)` | Gefälle ([core/packages/plates.has_slope](../core/packages/plates.py)): Decken, deren Oberseite überwiegend so flach geneigt ist, werden im Voxelgitter eben gemacht (tiefste bis höchste Stelle gefüllt). |
| `SLOPE_MIN_AREA_RATIO` | `0.5` | «überwiegend»: mindestens die Hälfte der Oberseite liegt in `SLOPE_DEG` |
| `TOP_MIN_NORMAL_Z` | `0.5` | als Oberseite zählen Flächen, die höchstens 60° geneigt sind (cos 60° = 0.5) |
| `PLATE_MAX_THICKNESS_RATIO` | `0.5` | plattenartig: Dicke höchstens die Hälfte der zweitkleinsten Kante |
| `PLATE_AXIS_SNAP_DEG` | `0.5` | Plattenrichtungen bis so nahe an x/y/z werden auf die Achse eingerastet (Modellierungsungenauigkeit, sonst entstehen schräge Voxeltreppen) |
| `WALL_MAX_NORMAL_Z` | `0.5` | Wand: Normale höchstens 30° aus der Waagrechten (Platte steiler als 60°) |
| `PACKAGE_PARALLEL_DEG` | `2.0` | Platten bilden nur ein Paket, wenn ihre Normalen höchstens so weit abweichen |
| `PACKAGE_COVERED_RATIO` | `0.9` | Glied gilt als abgedeckt (nicht freistehend), wenn so viel seiner Fläche an anderen Gliedern liegt; freistehende Glieder brauchen selbst die Mindestdicke |
| `PACKAGE_GAP_MIN_MM` | `10.0` | Spalt zwischen Schichten (real), der immer zum Paket zählt – auch wo die halbe Mindestwand kleiner wäre (sehr grosse Massstäbe). Festlegung. |

## Öffnungen

Code: [core/openings/](../core/openings/)

Fenster-/Türfüller ([core/openings/detection.find_hosts](../core/openings/detection.py)): Ein Füller gilt als parallel zur Ebene des Pakets, wenn seine Normale um höchstens `HOST_PARALLEL_DEG` abweicht. In einer Wand muss der Teil des Füllers mindestens diese Anteile seiner Breite bzw. Höhe abdecken – sonst ist die Wand kein Wirt (Leibung an einer Querwand, Gaubenwange).

| Konstante | Wert | Erklärung |
|---|---|---|
| `HOST_PARALLEL_DEG` | `10.0` |  |
| `HOST_MIN_WIDTH_RATIO` | `0.2` |  |
| `HOST_MIN_HEIGHT_RATIO` | `0.5` |  |
| `OPENING_MIN_WALLS` | `2.0` | Öffnungen werden nur ausgeschnitten oder vertieft, wenn sie mindestens so viele Mindestwände breit und hoch sind – schmalere Schlitze liessen sich nicht sauber drucken und bleiben geschlossen. |

## Geländer als Band

Code: [core/voxels/band.py](../core/voxels/band.py)

| Konstante | Wert | Erklärung |
|---|---|---|
| `RAILING_GAP_VOXELS` | `2` | so grosse Lücken zwischen Gebäude und Geländerunterkante werden geschlossen |
| `RAILING_MAX_LOST_RATIO` | `0.5` | Geländer entfällt, wenn mehr als die Hälfte seiner Spalten keine Auflage hat |

## Geschoss-, Dach- und Deckenteile

Code: [core/parts/](../core/parts/)

| Konstante | Wert | Erklärung |
|---|---|---|
| `CAVITY_FILL_RATIO` | `0.05` | Geschlossene Hohlräume eines Teils (Schacht, Zwischenraum unter einem Bodenaufbau) bis zu diesem Anteil seines Volumens werden gefüllt: unsichtbar, ohne Stützen im Innern druckbar und im Slicer keine Scheinobjekte. Grössere (z.B. ein geschlossener Dachraum) blieben sonst als viel Mehrmaterial – sie bleiben hohl, mit Warnung. |
| `ROOF_ZONE_MIN_HEIGHT_MM` | `1000` | Dachschale mindestens so hoch (real): Träger darin zählen zum Dach |

Geschossteile ([core/parts/](../core/parts/)), reale mm: Die Fuge zwischen zwei Geschossen bleibt eben. Absätze bis `JOINT_LEVELING_MM` unter der Fuge (Dämmung, Bekleidung unter einer Decke) werden abgeschnitten, Rücksprünge bis dahin über der Fuge aufgefüllt. Ein Vollabschnitt bis `JOINT_SLAB_MM` gilt als Decke (darüber: Wand); tiefer liegende Deckenbereiche, die breiter als `JOINT_WIDTH_MM` sind (z.B. TG-Dach neben dem Haus), werden nicht zerschnitten – liegen sie als Deckel über Räumen, werden sie ein eigenes Teil ([core/parts/storey_joints.ceiling_lids](../core/parts/storey_joints.py)).

| Konstante | Wert | Erklärung |
|---|---|---|
| `JOINT_LEVELING_MM` | `150.0` |  |
| `JOINT_SLAB_MM` | `1000.0` |  |
| `JOINT_WIDTH_MM` | `2000.0` |  |
| `JOINT_WALL_MAX_MM` | `500.0` | Deckel ([core/parts/storey_joints.ceiling_lids](../core/parts/storey_joints.py)): Wände bis zu dieser Dicke (real) zwischen zwei Deckenflächen gehören zum Deckel; schmalere Deckenstreifen (Stürze über Türen und Fenstern) bilden keinen. |
| `JOINT_OVERHANG_MM` | `500.0` | Tiefer als die Unterseite des Teils ragende Stücke (letzte Treppenstufen in der Deckenöffnung) gehen bis zu dieser Tiefe (real) ans Teil darunter, sonst hingen sie unter der Bodenplatte und höben das Teil vom Bett ab. |

Unterseite eben ([core/parts/storey_joints.flat_undersides](../core/parts/storey_joints.py)): Einstülpungen in der Unterseite eines Geschossteils, schmaler als `JOINT_RECESS_WIDTH_MM` (real, schmale Seite im Grundriss) und höchstens `JOINT_RECESS_DEPTH_MM` tief, werden bis zur Fuge gefüllt: Storenkasten-Rinnen (160–250 mm), Laibungsschlitze von Fenstern darunter, Fugen zwischen Bauteilen. Treppenaugen (ab ~900 mm) und durchgehende Schächte bleiben offen. Die Tiefe deckt Decke samt Bodenaufbau.

| Konstante | Wert | Erklärung |
|---|---|---|
| `JOINT_RECESS_WIDTH_MM` | `300.0` |  |
| `JOINT_RECESS_DEPTH_MM` | `500.0` |  |

Suchfenster um die Geschoss-Z (reale m), in dem die Deckenunterkante gesucht wird: nach unten tief genug für dicke, geebnete Bodenplatten samt Magerbeton, nach oben nur knapp.

| Konstante | Wert | Erklärung |
|---|---|---|
| `JOINT_SEARCH_WINDOW_BELOW_M` | `1.2` |  |
| `JOINT_SEARCH_WINDOW_ABOVE_M` | `0.2` |  |
| `JOINT_MIN_RISE` | `0.05` | Mindest-Anstieg der Voxelzahl (Anteil der Grundfläche), damit eine Schicht als Deckenunterkante gilt. Sonst: Schnitt auf Geschoss-Z + Warnung. |

Dächer werden eigene Teile, sofern sie mindestens diesen Anteil am Volumen haben; Inseln (abgetrennte Stücke eines Teils, kleiner als `ISLAND_RATIO` des Hauptstücks) gehen ans Nachbarteil.

| Konstante | Wert | Erklärung |
|---|---|---|
| `ROOF_MIN_RATIO` | `0.02` |  |
| `ISLAND_RATIO` | `0.25` |  |
| `SLIVER_MAX_VOXELS` | `64` | Lose Splitter: Stücke unter dieser Voxelzahl ohne jeden Kontakt zu einem Teil werden gelöscht. |
| `SMALL_PART_RATIO` | `0.01` | Ganze Teile unter diesem Anteil am Gesamtvolumen gehen ans Nachbarteil mit der grössten Kontaktfläche. |

Dachschale ([core/parts/roof.roof_part](../core/parts/roof.py)): Dachbauteile sind Dach, wenn sie steiler als `ROOF_INCLINATION_DEG` geneigt sind oder (flach) mehr als `ROOF_ABOVE_ELEVATION_MM` (real) über der Kote ihres Geschosses liegen.

| Konstante | Wert | Erklärung |
|---|---|---|
| `ROOF_INCLINATION_DEG` | `5.0` |  |
| `ROOF_ABOVE_ELEVATION_MM` | `1500.0` |  |

## Druckbett und Überhänge

Code: [core/parts/](../core/parts/)

Druckbett ([core/parts/print_layout.py](../core/parts/print_layout.py)), Modell-mm. Festlegung.

| Konstante | Wert | Erklärung |
|---|---|---|
| `PRINT_GAP_MM` | `8.0` | Abstand der Teile auf einem Druckbett |
| `PRINT_BED_SPACING_MM` | `100.0` | Abstand zweier Druckbetten in der Datei mit allen Teilen (trennt sie sichtbar) |
| `BRIDGE_MAX_MM` | `10.0` | Überhänge ([core/parts/overhangs.py](../core/parts/overhangs.py)), Modell-mm. FDM überbrückt waagrechte Strecken bis etwa 10 mm sauber, wenn sie beidseitig aufliegen (PLA/PETG mit Lüfter); längere Brücken hängen durch und brauchen Stützen. |
| `OVERHANG_MIN_MM2` | `25.0` | Kleinere Stützflächen je Teil werden nicht gemeldet (einzelne Voxel an Kanten, Stützenköpfe). 25 mm² = 5 × 5 mm. |
| `OVERHANG_ON_MODEL_RATIO` | `0.5` | Liegt mindestens dieser Anteil der Stützfläche über dem Modell statt über dem Bett, lautet der Vorschlag «anders zuordnen»: Stützen in den Räumen eines Massstabsmodells lassen sich kaum entfernen. |

## Steckverbinder

Code: [core/connectors/](../core/connectors/)

Steckverbinder ([core/connectors/planning.py](../core/connectors/planning.py)), Modell-mm. Nur dort, wo das untere Teil die Decke darüber trägt (Wandkronen, Stützenköpfe): Zapfen als Kegelstumpf auf der Krone, Tasche in der Deckenunterseite. Das obere Teil wird nur aufgelegt (kein Einrasten). Rechteckig auf länglichen Kontaktflächen (Wände), rund auf gedrungenen (Stützen, Ecken). Masse gelten an der Kontaktfläche.

| Konstante | Wert | Erklärung |
|---|---|---|
| `CLEARANCE_MM` | `0.20` | Luft zwischen Zapfen und Tasche, ringsum und oben. Fallback: im Betrieb gilt clearance_mm des Druckerprofils ([db/seed/profile.csv](../db/seed/profile.csv), ebenfalls 0.20 mm) |
| `PEG_ROUND_DIAMETER_MM` | `(3.0, 2.4, 2.0, 1.6, 1.2)` | grösster passender Durchmesser gewinnt; min. 1.2 |
| `PEG_RECT_WIDTH_MM` | `(2.0, 1.6, 1.2)` | Breite quer zur Wand; Länge = 2 × Breite (min. 1.2 × 2.4) |
| `PEG_TAPER_DEG` | `15.0` | Flankenneigung gegen die Senkrechte: oben schmaler, leicht aufzusetzen |
| `PEG_DEPTH_RATIO` | `0.6` | Zapfenhöhe = Anteil der Deckendicke über dem Zapfen (Tasche bleibt Sackloch) |
| `PEG_MAX_ENGAGEMENT_MM` | `3.0` | Obergrenze der Zapfenhöhe, auch bei dicken Decken (Festlegung) |
| `MIN_ENGAGEMENT_MM` | `0.5` | kürzerer Zapfen führt nicht → kein Verbinder an dieser Stelle |
| `ELONGATION_RATIO` | `2.0` | Kontaktfläche (lokal) mindestens so lang wie breit × `ELONGATION_RATIO` → Rechteck |
| `OVERLAP_MM` | `0.4` | Zapfen taucht in die Wand ein (vermeidet koplanare Flächen beim Boolean) |
| `CYLINDER_SEGMENTS` | `48` | Kreis als 48-Eck: bei 3 mm Durchmesser weicht die Sehne höchstens 0.003 mm vom Kreis ab, weit unter der Druckgenauigkeit |
| `CONNECTORS_PER_JOINT` | `3` | drei Punkte: das obere Teil liegt statisch bestimmt auf |
| `CONNECTOR_MIN_SPACING_MM` | `10.0` | Mindestabstand zweier Verbinder derselben Fuge: die Punkte verteilen sich |
| `CONTACT_MIN_COLUMNS` | `40` | kleinere vertikale Berührungen zweier Teile (Anzahl Voxelsäulen, bei 0.4 mm Pitch 6.4 mm²) bekommen keine Verbinder |
| `CONTACT_MIN_PLANE_RATIO` | `0.2` | Kontaktebenen unter 20 % der grössten Ebene zweier Teile (Absätze, Podeste) bekommen keine Verbinder |
| `CONTACT_SHAPE_RADIUS_MM` | `3.0` | Umkreis, in dem die Form der Kontaktfläche bestimmt wird (länglich → Rechteck) |
| `CONNECTOR_MAX_VOLUME_CHANGE` | `0.2` | Boolean-Ergebnis verwerfen (Teil bleibt ohne Verbinder), wenn sich das Volumen um mehr als 20 % ändert – Schutz vor fehlerhaften Booleans |

## Kalkulation

Code: [core/output/estimate.py](../core/output/estimate.py)

Kalkulation (Schätzung, Festlegung – nicht mit Slicer-Werten abgeglichen)

| Konstante | Wert | Erklärung |
|---|---|---|
| `VOLUME_FACTOR` | `0.4` | Anteil des Hüllvolumens, der real als Filament anfällt (Wände + Infill) |
| `THROUGHPUT_CM3_H` | `10.0` | effektiver Volumendurchsatz des Druckers |
| `LAYER_CHANGE_H` | `0.001` | Zeitzuschlag je Layer (= 3.6 s: Fahrwege, Z-Hub) |

## Oberfläche und Ausgabe

Code: [ui/](../ui/)

| Konstante | Wert | Erklärung |
|---|---|---|
| `START_MODEL` | `"testdaten/MFH_eBKPH_Real.ifc"` | Beispielmodell, das beim Öffnen der Seite erscheint (fehlt die Datei: ohne Beispiel) |
| `VIEWER_MAX_FACES` | `200_000` | Dreiecksbudget nur der Vorschau im Browser (Festlegung); die STL bleibt vollständig |
| `PANGO_DLL_DIR` | `r"C:\msys64\mingw64\bin"` | Pango für WeasyPrint (PDF-Report) unter Windows, aus MSYS2 (README) |

| Konstante | Wert | Erklärung |
|---|---|---|
| `OUTPUT_TARGET_DEFAULT` | `"fdm"` | Ausgabeziel beim Start |
