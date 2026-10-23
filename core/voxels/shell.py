"""Hülle: Bauteile → gemeinsames Voxelgitter → wasserdichtes Mesh.

Diese Datei setzt die Bauteile zum Gesamtgitter zusammen (``voxelize``) und bremst, bevor der
Speicher überläuft (``check_grid``). Die Einzelschritte stehen in eigenen Modulen:
  * core/voxels/mesh_voxels.py      Netz → Voxel (Oberfläche, Innenraum nach Windungszahl)
  * core/voxels/element_voxels.py   Voxel eines Bauteils: mindestens 1 Voxel dick, Rückfall bei offenem Netz,
                             Verdicken (nur ausserhalb von Paketen; Wände und Decken skaliert
                             core/packages/grouping.py), Gefälle, Öffnungen aussparen
  * core/voxels/grid.py       ``VoxelGrid`` und ``BuildingElement``
  * core/voxels/meshing.py          Marching Cubes, Glättung, Dezimierung

Danach werden alle Bauteile in ein gemeinsames Gitter geodert. 1-Voxel-Spalten
(z.B. zwischen einer gerasteten Wand und ihrem Anschluss) werden geschlossen.
Fenster und Türen wirken erst auf dieses gemeinsame Gitter (VoxelGrid.place,
siehe core/openings/windows.py).

Eingabe: Liste von ``BuildingElement`` (Modellmass [mm]), Pitch und Massstab
Ausgabe: ``VoxelGrid`` mit Grundrissen, Dach-Labels und Warnungen
"""

from collections.abc import Callable
from typing import NamedTuple

import numpy as np
import psutil
from scipy.ndimage import binary_fill_holes

from config import BYTES_PER_VOXEL, GRID_MAX_VOXELS, GRID_RAM_RATIO, MAX_CAVITY_THICKNESS_MM
from core.voxels.element_voxels import cut_voids, element_voxel, flatten, thicken
from core.voxels.grid import BuildingElement, VoxelGrid


class _ElementVoxels(NamedTuple):
    """Voxel eines Bauteils samt seinem Ursprung ``lo`` (Gitter-Indizes) im Gesamtgitter."""
    voxels: np.ndarray
    lo: np.ndarray
    element: BuildingElement


def voxelize(building_elements: list[BuildingElement], pitch_mm: float, scale: int,
                 progress: Callable[[int, int], None] | None = None) -> VoxelGrid:
    """Legt alle Bauteile in ein gemeinsames Voxelgitter (samt Grundrissen und Dach-Labels).

    ``progress(i, n)`` wird nach jedem Bauteil gerufen. Ein Bauteil, das sich nicht
    voxelisieren lässt (defektes Netz), wird übersprungen und in ``warnings`` gemeldet,
    statt die ganze Erzeugung abzubrechen.
    """
    if not building_elements:
        raise ValueError("Keine Bauteile zum Voxelisieren.")
    max_thickness = max(1, round(MAX_CAVITY_THICKNESS_MM / (pitch_mm * scale)))
    parts, warnings = _voxelize_each(building_elements, pitch_mm, max_thickness, progress)
    if not parts:
        raise ValueError("Kein Bauteil liess sich voxelisieren – Geometrie im IFC prüfen.")
    return _combine(parts, pitch_mm, warnings)


def _voxelize_each(building_elements: list[BuildingElement], pitch_mm: float, max_thickness: int,
                    progress: Callable[[int, int], None] | None) -> tuple[list[_ElementVoxels], list[str]]:
    """Voxelisiert jedes Bauteil für sich; nicht voxelisierbare werden übersprungen und gemeldet."""
    parts, warnings = [], []
    for number, building_element in enumerate(building_elements, start=1):
        try:
            voxels, lo = element_voxel(building_element.mesh.triangles / pitch_mm, max_thickness)
            voxels, lo = thicken(voxels, lo, building_element.thickening)
            if building_element.flatten:
                voxels = flatten(voxels)
            voxels, is_open = cut_voids(voxels, lo, building_element.voids, pitch_mm)
            if is_open:
                warnings.append(f"Bauteil {building_element.guid or number}: {is_open} Öffnung(en) mit offenem Körper nicht ausgeschnitten.")
            parts.append(_ElementVoxels(voxels, lo, building_element))
        except (ValueError, IndexError, MemoryError) as error:
            warnings.append(f"Bauteil {building_element.guid or number} übersprungen: {error}")
        if progress:
            progress(number, len(building_elements))
    return parts, warnings


def _combine(parts: list[_ElementVoxels], pitch_mm: float, warnings: list[str]) -> VoxelGrid:
    """Odert die Bauteil-Voxel in ein Gesamtgitter und führt Grundrisse je Geschoss und Dach-Labels mit."""
    lo_overall = np.min([p.lo for p in parts], axis=0)
    hi_overall = np.max([p.lo + p.voxels.shape for p in parts], axis=0)
    check_grid(tuple(int(n) for n in hi_overall - lo_overall), pitch_mm)
    matrix = np.zeros(tuple(hi_overall - lo_overall), dtype=bool)
    roof_names = sorted({p.element.roof for p in parts if p.element.roof})
    roof = np.full(matrix.shape, -1, dtype=np.int8) if roof_names else None
    floor_plans: dict[str, np.ndarray] = {}
    for voxels, lo, building_element in parts:
        a = lo - lo_overall
        b = a + voxels.shape
        target = (slice(a[0], b[0]), slice(a[1], b[1]), slice(a[2], b[2]))
        matrix[target] |= voxels
        if building_element.roof:
            roof[target][voxels] = roof_names.index(building_element.roof)
        elif building_element.storey:
            floor_plan = floor_plans.setdefault(building_element.storey, np.zeros(matrix.shape[:2], dtype=bool))
            floor_plan[target[:2]] |= voxels.any(axis=2)
    floor_plans = {name: binary_fill_holes(g) for name, g in floor_plans.items()}   # Räume einschliessen
    return VoxelGrid(close_gaps(matrix), lo_overall * pitch_mm, pitch_mm,
                       floor_plans=floor_plans, roof=roof, roof_names=roof_names, warnings=warnings)


def close_gaps(matrix: np.ndarray) -> np.ndarray:
    """Füllt Spalten und Löcher von genau 1 Voxel: Voxel, die entlang einer Achse beidseitig belegt sind.

    Ein 1-Voxel-Spalt ist nicht druckbar und entsteht nur, wo das Rasten eine Fläche
    minim verschoben hat. Breitere Spalten, Ecken und Treppenstufen bleiben unverändert.
    """
    m = np.pad(matrix, 1)
    slit = np.zeros_like(m)
    for axis in range(3):
        slit |= np.roll(m, 1, axis=axis) & np.roll(m, -1, axis=axis)
    return (m | slit)[1:-1, 1:-1, 1:-1]


# --- Speicherbremse -----------------------------------------------------------

def ram_bytes() -> int | None:
    """Physischer Arbeitsspeicher des Rechners (psutil, auch unter Windows; None, wenn nicht lesbar)."""
    try:
        return int(psutil.virtual_memory().total)
    except (OSError, RuntimeError):
        return None


def grid_limit() -> int:
    """Grösste zulässige Voxelzahl: GRID_MAX_VOXELS, auf kleineren Rechnern weniger (RAM-Anteil)."""
    ram = ram_bytes()
    return GRID_MAX_VOXELS if ram is None else min(GRID_MAX_VOXELS, int(ram * GRID_RAM_RATIO / BYTES_PER_VOXEL))


def check_grid(form: tuple[int, int, int], pitch_mm: float) -> None:
    """Bricht mit klarer Meldung ab, bevor ein Gitter angelegt wird, das den Speicher sprengt."""
    n = int(np.prod(np.asarray(form, dtype=np.int64)))
    if n > (limit_value := grid_limit()):
        dimensions = " × ".join(f"{k * pitch_mm:.0f}" for k in form)
        raise ValueError(f"Modell zu gross für das Voxelgitter ({dimensions} mm, {n / 1e6:.0f} Mio. Voxel, "
                         f"≈ {n * BYTES_PER_VOXEL / 1e9:.0f} GB; Grenze {limit_value / 1e6:.0f} Mio.). "
                         "Qualität «entwurf», einen grösseren Massstab wählen oder Ausreisser entfernen.")
