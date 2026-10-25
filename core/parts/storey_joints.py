"""Fugen zwischen den Geschossen: Höhe finden und je Spalte glätten.

Zwischen zwei Geschossteilen liegt eine Fuge. Ihre Höhe entsteht in drei Schritten:
  1. ``cuts``: Fuge je Geschossgrenze = Deckenunterkante im Suchfenster um die Geschoss-Z,
     gezählt nur dort, wo dieses oder ein höheres Geschoss steht (Grundrisse seiner
     IFC-Bauteile). Ausserhalb gibt es keine Fuge – ein tieferer Gebäudeflügel wird
     nicht von der Fuge eines höheren geschnitten.
  2. ``flush_slabs``: Eine Decke, die bündig an der Fuge liegt und über den Grundriss hinausragt,
     erweitert die Fuge: Eine Decke gehört zum Teil darüber, das untere Teil bleibt oben offen.
  3. ``smooth_joint``: Fuge je Spalte glätten: kleine Absätze unter der Fuge (Dämmung unter der
     Decke) abschneiden, kleine Rücksprünge darüber auffüllen → die Unterseite des oberen
     Teils bleibt eben. Breite, tiefer liegende Deckenbereiche (TG-Dach neben dem
     Haus) gehen zunächst ganz ans untere Teil, statt zerschnitten zu werden.
Danach trennt ``ceiling_lids`` solche tiefer liegenden Decken als eigenes Teil vom unteren ab
(core/parts/partitioning.py): Als Deckel bräuchten sie Stützen in den Räumen darunter. Zum Schluss füllt
``flat_undersides`` schmale Einstülpungen in der Unterseite jedes Geschossteils (Storenkasten, Laibungsschlitze).

Falle (verifiziert am NEST-Modell): ``IfcBuildingStorey.Elevation`` ist relativ
(EG = 0.0, Wände aber ab 432.6 m Welt-Z). Die Fugenhöhe kommt deshalb aus der
ObjectPlacement im Weltsystem (``storey_heights``).

Eingabe: Voxelgitter, Geschosshöhen [(Name, Welt-Z)], Grundrisse je Geschoss
Ausgabe: Schichtbereich [k_from, k_to) je Geschoss (``cuts``) bzw. Fugenhöhe je Spalte (``smooth_joint``)
"""

import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np
from scipy.ndimage import binary_closing, binary_opening, label

from config import JOINT_MIN_RISE, JOINT_SEARCH_WINDOW_ABOVE_M, JOINT_SEARCH_WINDOW_BELOW_M
from core.ifc.assignment import room_names
from core.voxels.grid import VoxelGrid


def storey_heights(model: ifcopenshell.file, scale: int) -> list[tuple[str, float]]:
    """(eindeutiger Name, Welt-Z im Modellmass [mm]) je IfcBuildingStorey, aufsteigend."""
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(model)   # Projekteinheit → m
    names = room_names(model)
    heights = []
    for s in model.by_type("IfcBuildingStorey"):
        if s.ObjectPlacement is None:
            continue
        z = ifcopenshell.util.placement.get_local_placement(s.ObjectPlacement)[2, 3]
        heights.append((names[s.id()], float(z) * unit_scale * 1000.0 / scale))
    return sorted(heights, key=lambda h: h[1])


def cuts(voxel_grid: VoxelGrid, storeys: list[tuple[str, float]], scale: int,
             floor_plans: dict[str, np.ndarray] | None = None) -> tuple[list[tuple[str, int, int]], list[str]]:
    """Z-Schichtbereich [k_from, k_to) je Geschoss (Fugenebenen) und Warnungen.

    Die Fuge unter Geschoss n liegt im Suchfenster um seine Z-Höhe dort, wo die
    Voxelzahl je Schicht am stärksten ansteigt (= Unterkante der Decke). Mit
    ``floor_plans`` (Geschoss → 2D-Maske) zählen nur die Spalten im Grundriss von n.
    """
    if len(storeys) < 2:
        return [(storeys[0][0] if storeys else "Modell", 0, voxel_grid.matrix.shape[2])], []

    nz = voxel_grid.matrix.shape[2]

    def layer_index(z_mm: float) -> int:
        return int(round((z_mm - voxel_grid.origin[2]) / voxel_grid.pitch))

    boundaries, warnings = [0], []
    for name, z in storeys[1:]:
        columns = joint_columns(voxel_grid, floor_plans, name)
        per_layer = voxel_grid.matrix[columns].sum(axis=0).astype(np.int64)
        base_area = max(1, int(voxel_grid.matrix[columns].any(axis=1).sum()))
        start_idx = max(1, layer_index(z - JOINT_SEARCH_WINDOW_BELOW_M * 1000 / scale))
        stop_idx = min(nz - 1, layer_index(z + JOINT_SEARCH_WINDOW_ABOVE_M * 1000 / scale))
        cut = layer_index(z)
        if stop_idx > start_idx:
            rise = per_layer[start_idx:stop_idx + 1] - per_layer[start_idx - 1:stop_idx]
            j = int(np.argmax(rise))
            if rise[j] >= JOINT_MIN_RISE * base_area:
                cut = start_idx + j
            else:
                warnings.append(f"Fuge bei «{name}»: keine klare Deckenunterkante – Schnitt auf Geschoss-Z.")
        boundaries.append(min(max(cut, boundaries[-1] + 1), nz - 1))
    boundaries.append(nz)
    ranges = [(name, boundaries[i], boundaries[i + 1]) for i, (name, _) in enumerate(storeys)]
    return ranges, warnings


def joint_columns(voxel_grid: VoxelGrid, floor_plans: dict[str, np.ndarray] | None, name: str) -> np.ndarray:
    """2D-Maske der Spalten, in denen die Fuge des Geschosses gilt (ohne Angabe: überall)."""
    g = (floor_plans or {}).get(name)
    return g if g is not None and g.any() else np.ones(voxel_grid.matrix.shape[:2], dtype=bool)


def storey_and_above(voxel_grid: VoxelGrid, storeys: list[tuple[str, float]],
                 floor_plans: dict[str, np.ndarray] | None) -> dict[str, np.ndarray] | None:
    """Je Geschoss die Spalten, in denen es ODER ein höheres Geschoss steht (dort gilt seine Fuge)."""
    if not floor_plans:
        return None
    union_mask = np.zeros(voxel_grid.matrix.shape[:2], dtype=bool)
    result = {}
    for name, _ in reversed(storeys):
        if (g := floor_plans.get(name)) is not None:
            union_mask = union_mask | g
        result[name] = union_mask.copy()
    return result


def flush_slabs(m: np.ndarray, k: int, columns: np.ndarray, leveling: int, plate: int) -> np.ndarray:
    """Fugenspalten samt den bündigen Decken, die mit der Decke im Grundriss zusammenhängen (2D-Maske).

    Bündig: Material bei k, das höchstens ``plate`` Voxel nach oben reicht (keine Wand, die durch die Fuge läuft),
    darunter höchstens ``leveling`` Voxel (Deckenunterseite an der Fuge) oder eine Wand (länger als ``plate``),
    auf der die Decke liegt. Tiefer liegende Decken (dazwischen) zählen nicht – sie trennt ``ceiling_lids``.
    """
    return _with_flush_slabs(m[:, :, k], _run_length(m, k, 1, plate + 1), _run_length(m, k - 1, -1, plate + 1),
                             columns, leveling, plate)


def _with_flush_slabs(layer: np.ndarray, top: np.ndarray, bottom: np.ndarray, columns: np.ndarray, leveling: int,
                      plate: int) -> np.ndarray:
    """``flush_slabs`` mit schon gezählten Vollabschnitten über (``top``) und unter (``bottom``) der Fuge."""
    flush = layer & (top <= plate) & ((bottom <= leveling) | (bottom > plate))
    # Mit den Fugenspalten zusammen beschriften: die Aussenwände des oberen Geschosses stehen auf der Decke und
    # trennen sie sonst in «innen» und «aussen».
    regions, _ = label(flush | columns, structure=np.ones((3, 3), dtype=bool))
    touching = np.unique(regions[columns])
    return columns | (np.isin(regions, touching[touching > 0]) & flush)


def ceiling_lids(part: np.ndarray, k_next: int, window: int, plate: int, wall: int) -> list[tuple[np.ndarray, int]]:
    """Deckel eines Geschossteils: Decken, die das Teil oben abschliessen und unter denen ein Raum des Teils liegt.

    ``part``: Maske des Teils; ``k_next``: Fuge zum Geschoss darüber (Schicht). Je Spalte zählt der oberste
    Vollabschnitt (höchstens ``plate`` Voxel), wenn seine Oberseite im Suchfenster der Fuge liegt (ab
    ``k_next - window``) und unter ihm Luft und weiter unten wieder das Teil liegt. Schmale Stellen (Stürze,
    schmaler als 2 × ``wall``) zählen nicht; Wände bis 2 × ``wall`` Voxel Dicke zwischen zwei Deckelflächen gehören
    zur Fläche. Jede Fläche wird waagrecht an ihrer häufigsten Deckenunterseite geschnitten; Wände darunter bleiben
    beim Teil. Rückgabe je Deckel: (2D-Maske der Fläche, unterste Schicht des Deckels).
    """
    z0 = max(0, k_next - window - plate - 1)                         # nur das Suchfenster ansehen (Speicher)
    sub = part[:, :, z0:]
    nz = sub.shape[2]
    has = sub.any(axis=2)
    top = np.where(has, nz - 1 - np.argmax(sub[:, :, ::-1], axis=2), -1)
    layer = np.arange(nz)[None, None, :]
    air = ~sub & (layer < top[:, :, None])
    gap = np.where(air.any(axis=2), nz - 1 - np.argmax(air[:, :, ::-1], axis=2), -1)   # oberste Luft unter top
    below = np.logical_or.accumulate(sub, axis=2)                   # irgendwo darunter liegt das Teil
    floor = part[:, :, :z0].any(axis=2) | (
        (gap >= 1) & np.take_along_axis(below, np.maximum(gap - 1, 0)[:, :, None], axis=2)[:, :, 0])
    near = has & (top + z0 >= k_next - window)
    slab = near & (gap >= 0) & (top - gap <= plate) & floor
    areas = binary_opening(slab, structure=np.ones((3, 3), dtype=bool), iterations=wall + 1)
    if not areas.any():
        return []
    # gepolstert schliessen: sonst frisst das Schliessen den Deckel am Gitterrand an (dort steht die Aussenwand)
    areas = binary_closing(np.pad(areas, wall), structure=np.ones((3, 3), dtype=bool), iterations=wall)[
        wall:-wall, wall:-wall] & near if wall else areas
    regions, n = label(areas, structure=np.ones((3, 3), dtype=bool))
    lids = []
    for number in range(1, n + 1):
        region = regions == number
        undersides = gap[region & slab] + 1
        if len(undersides):
            lids.append((region, z0 + int(np.bincount(undersides).argmax())))   # häufigste Deckenunterseite
    return lids


def flat_undersides(labels: np.ndarray, m: np.ndarray, joints: list[tuple[int, int, np.ndarray]], depth: int,
                    radius: int) -> dict[int, tuple[int, int]]:
    """Füllt schmale Einstülpungen in der Unterseite der Geschossteile bis zur Fuge (verändert ``labels`` und ``m``).

    ``joints``: je Geschossteil (Label, Fugenschicht k, 2D-Maske der Spalten mit Fuge bei k). Einstülpung = Spalte, in der
    die unterste Schicht des Teils 1 bis ``depth`` Voxel über k liegt (Storenkasten-Rinne, Laibungsschlitz eines Fensters
    darunter, Fuge zwischen Bauteilen). Gefüllt werden nur schmale – Bereiche, die eine Öffnung mit Radius ``radius``
    überstehen (Treppenauge), bleiben – und nur über Luft oder Voxeln tieferer Geschosse; Dächer und Deckel bleiben.
    Läuft vor dem Vernetzen und den Steckverbindern: deren Taschen entstehen erst danach im Netz.
    Rückgabe je Teil mit Füllung: (Anzahl Einstülpungen, gefüllte Voxel).
    """
    result = {}
    for part_label, k, columns in joints:
        top = min(labels.shape[2], k + depth + 1)
        window = labels[:, :, k:top]                                        # Sicht: Schreiben wirkt auf ``labels``
        part = window == part_label
        lift = part.argmax(axis=2)                                          # Schichten zwischen Fuge und Unterseite
        recess = columns & part.any(axis=2) & (lift > 0)
        if not recess.any():
            continue
        narrow = recess & ~binary_opening(recess, structure=np.ones((3, 3), dtype=bool), iterations=radius)
        below = np.arange(top - k)[None, None, :] < lift[:, :, None]
        narrow &= ~(below & (window > part_label)).any(axis=2)             # Dach- oder Deckelvoxel: nicht anfassen
        fill = narrow[:, :, None] & below
        if fill.any():
            window[fill] = part_label
            m[:, :, k:top] |= fill
            result[part_label] = (label(narrow, structure=np.ones((3, 3), dtype=bool))[1], int(fill.sum()))
    return result


def _run_length(m: np.ndarray, start: int, step: int, n: int) -> np.ndarray:
    """Je Spalte: Anzahl aufeinanderfolgender True ab Schicht ``start`` in Richtung ``step`` (max. n)."""
    tally = np.zeros(m.shape[:2], dtype=np.int32)
    running = np.ones(m.shape[:2], dtype=bool)
    for d in range(n):
        k = start + step * d
        if not 0 <= k < m.shape[2]:
            break
        running &= m[:, :, k]
        tally += running
    return tally


def smooth_joint(m: np.ndarray, k: int, columns: np.ndarray, leveling: int, plate: int,
                  width: int, flush: bool = False) -> np.ndarray:
    """Glättet die Fuge auf Schicht ``k`` (verändert ``m``) und liefert die Fugenhöhe je Spalte.

    In den ``columns`` (2D-Maske) gilt je Spalte (Zahlen in Voxeln):
      * Vollabschnitt durch die Fuge länger als ``plate`` → Wand: Fuge bei k.
      * Decke oder Wand, die höchstens ``leveling`` unter die Fuge ragt (darunter leer) → der
        Überstand wird abgeschnitten (Dämmung/Bekleidung, Deckenunterseite unter einer Wand des
        oberen Geschosses); sonst bliebe er als dünne Schicht oben auf dem unteren Teil liegen.
      * Decke, die tiefer ragt und zu einem mindestens ``width`` breiten Bereich gehört
        (tiefer liegende Decke) → Fuge über der Decke: sie geht ganz ans untere Teil.
        Schmale Bereiche (Unterzug) werden bei k geschnitten.
      * Leer bei k, aber Material höchstens ``leveling`` darüber → bis k aufgefüllt.
    Ausserhalb der ``columns`` keine Fuge (Höhe = Gitterhöhe). ``flush``: die Spalten erst um bündige Decken
    erweitern (``flush_slabs``, mit denselben Vollabschnitten gezählt).
    """
    nz = m.shape[2]
    top = _run_length(m, k, 1, plate + 1)
    bottom = _run_length(m, k - 1, -1, plate + 1)
    if flush:
        columns = _with_flush_slabs(m[:, :, k], top, bottom, columns, leveling, plate)
    height = np.where(columns, k, nz).astype(np.int32)
    full = m[:, :, k] & columns
    slab = full & (top + bottom <= plate)
    trim = full & (bottom <= leveling)
    deep = slab & (bottom > leveling)
    if width > 0 and deep.any():
        deep = binary_opening(deep, structure=np.ones((3, 3), dtype=bool), iterations=width)
    height[deep] = k + top[deep]
    gap = _run_length(~m, k, 1, leveling + 1)
    fill_up = columns & ~m[:, :, k] & (gap <= leveling) & (k + gap < nz)
    for d in range(1, leveling + 1):
        if k - d >= 0:
            m[:, :, k - d] &= ~(trim & (bottom >= d))
    for d in range(leveling):
        if k + d < nz:
            m[:, :, k + d] |= fill_up & (gap > d)
    return height
