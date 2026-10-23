"""Aktion «band»: Geländer als dünne Scheibe vom Boden bis zur Geländerhöhe.

Ein Geländer besteht aus Stäben (2 cm → 0.1 mm bei 1:200) und verschwindet beim Voxelisieren;
ein Füllquader (Bounding Box) füllt bei L-förmigen Geländern den ganzen Balkon. Darum:

1. Netz oberflächen-voxelisieren auf dem Raster des Hauptgitters – jede berührte Zelle zählt,
   auch bei Teilen dünner als ein Voxel (Glasgeländer).
2. Fussabdruck = Projektion in den Grundriss.
3. Auf ``width_voxel`` verbreitern; übrig bleiben nur Spalten, unter denen Gebäude liegt –
   so wächst das Band zur Balkon-/Deckenseite und steht sicher auf.
4. Je Spalte füllen: vom obersten Gebäudevoxel darunter (Lücke ≤ config.RAILING_GAP_VOXELS wird geschlossen)
   bis zum höchsten Geländervoxel. Gerade, L-förmige, gebogene und geneigte (Treppe) Geländer
   gehen damit gleich.
5. Spalten ohne Gebäude darunter fallen weg; fällt mehr als die Hälfte weg, entfällt das Geländer.

Grenze: Steht ein Geländer mitten auf einer Decke (Gebäude auf beiden Seiten), wird das Band
2·(breite−1)+1 Voxel breit statt ``width`` – üblich sind Geländer am Deckenrand.

Eingabe: Geländer-Netz (Modell-mm), Voxelgitter, Bandbreite in Voxeln
Ausgabe: ``RailingBand`` (oder None) samt Anteil weggefallener Spalten; ``place`` schreibt es ins Gitter
"""

from dataclasses import dataclass

import numpy as np
import trimesh
from scipy.ndimage import maximum_filter, minimum_filter

from config import RAILING_GAP_VOXELS, RAILING_MAX_LOST_RATIO
from core.analysis.ruleset import ScaleParameters
from core.ifc.model import IfcModel
from core.parts.roof import roof_name
from core.voxels.grid import VoxelGrid
from core.voxels.mesh_voxels import surface_voxel

_EMPTY = np.iinfo(np.int32).max


@dataclass
class RailingBand:
    """Voxel eines Geländerbands in Gitterindizes: Spalten (i, j) mit Schichten k_from..k_to (inklusive)."""
    i: np.ndarray
    j: np.ndarray
    k_from: np.ndarray
    k_to: np.ndarray


def extend_grid(voxel_grid: VoxelGrid, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Vergrössert das Gitter (samt Grundrissen und Dach-Labels), bis die Indizes [lo, hi) hineinpassen.

    Rückgabe: Verschiebung der alten Indizes (neu = alt + versatz).
    """
    form = np.array(voxel_grid.matrix.shape)
    pad_before = np.maximum(0, -lo)
    after = np.maximum(0, hi - form)
    if not (pad_before.any() or after.any()):
        return np.zeros(3, dtype=np.int64)
    margin = list(zip(pad_before, after))
    voxel_grid.matrix = np.pad(voxel_grid.matrix, margin)
    if voxel_grid.roof is not None:
        voxel_grid.roof = np.pad(voxel_grid.roof, margin, constant_values=-1)
    voxel_grid.floor_plans = {n: np.pad(g, margin[:2]) for n, g in voxel_grid.floor_plans.items()}
    voxel_grid.origin = voxel_grid.origin - pad_before * voxel_grid.pitch
    return pad_before.astype(np.int64)


def band(mesh: trimesh.Trimesh, voxel_grid: VoxelGrid, width_voxel: int) -> tuple[RailingBand | None, float]:
    """Plant das Band eines Geländers im (ggf. erweiterten) Gitter; (Band oder None, Anteil weggefallener Spalten)."""
    p = voxel_grid.pitch
    triangles = (mesh.triangles - voxel_grid.origin) / p
    points = triangles.reshape(-1, 3)
    lo = np.rint(points.min(axis=0)).astype(np.int64)
    size = np.rint(points.max(axis=0)).astype(np.int64) - lo + 1
    r = width_voxel - 1
    offset = extend_grid(voxel_grid, lo - [r, r, 0], lo + size + [r, r, 0])
    lo = lo + offset
    cells = surface_voxel(triangles + offset, lo, size)        # lokal: [i, j, k] ab lo
    if not cells.any():
        return None, 1.0

    footprint, top, bottom = _widened(cells, r)
    wide = top >= 0
    lo2 = lo - [r, r, 0]

    ii, jj = np.nonzero(wide)
    gi, gj = ii + lo2[0], jj + lo2[1]
    k_top = top[ii, jj] + lo[2]
    k_bottom = bottom[ii, jj] + lo[2]
    building = _highest_building(voxel_grid, gi, gj, k_top)
    standing = (building >= 0) & (building >= k_bottom - 1 - RAILING_GAP_VOXELS)

    original = footprint[ii, jj]
    lost_ratio = 1.0 - standing[original].mean() if original.any() else 1.0
    if not standing.any() or lost_ratio > RAILING_MAX_LOST_RATIO:
        return None, lost_ratio
    return RailingBand(gi[standing], gj[standing], building[standing] + 1, k_top[standing]), lost_ratio


def _widened(cells: np.ndarray, r: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fussabdruck, höchste und tiefste Geländerschicht je Spalte, um ``r`` je Seite verbreitert."""
    footprint = cells.any(axis=2)
    k = np.arange(cells.shape[2])
    top = np.where(cells, k, -1).max(axis=2)                          # höchste Geländerschicht je Spalte
    bottom = np.where(cells, k, _EMPTY).min(axis=2)
    # verbreitern um r je Seite (symmetrisch); aussen fällt es mangels Gebäude darunter wieder weg
    footprint = np.pad(footprint, r)
    top = maximum_filter(np.pad(top, r, constant_values=-1), size=2 * r + 1, mode="constant", cval=-1)
    bottom = minimum_filter(np.pad(bottom, r, constant_values=_EMPTY), size=2 * r + 1, mode="constant", cval=_EMPTY)
    return footprint, top, bottom


def _highest_building(voxel_grid: VoxelGrid, gi: np.ndarray, gj: np.ndarray, k_top: np.ndarray) -> np.ndarray:
    """Oberstes Gebäudevoxel je Spalte bis zur Geländeroberkante (−1 = kein Gebäude darunter)."""
    voxel_columns = voxel_grid.matrix[gi, gj, :]
    deep = np.arange(voxel_columns.shape[1])
    return np.where(voxel_columns & (deep[None, :] <= k_top[:, None]), deep[None, :], -1).max(axis=1)


def place(voxel_grid: VoxelGrid, b: RailingBand, storey: str = "", roof: str | None = None) -> None:
    """Schreibt ein Band ins Gitter und ordnet es dem Geschoss- bzw. Dachteil zu."""
    for i, j, k0, k1 in zip(b.i, b.j, b.k_from, b.k_to):
        if k1 < k0:
            continue
        voxel_grid.matrix[i, j, k0:k1 + 1] = True
        if roof is not None and voxel_grid.roof is not None and roof in voxel_grid.roof_names:
            voxel_grid.roof[i, j, k0:k1 + 1] = voxel_grid.roof_names.index(roof)
    if roof is None and storey in voxel_grid.floor_plans:
        voxel_grid.floor_plans[storey][b.i, b.j] = True


def place_railing_bands(ifc: IfcModel, voxel_grid: VoxelGrid, railing: list, parameter: ScaleParameters,
                        elevations: dict[str, float], zones: dict) -> list[str]:
    """Geländer (Aktion «band») als Scheibe ins Gitter, vor den Öffnungen; Rückgabe: Warnungen.

    ``railing``: Paare (Zeile der Bauteiltabelle, Netz im Modellmass). ``elevations`` und ``zones``
    entscheiden, ob ein Geländer zu einem Dachteil gehört (core/parts/roof.py).
    """
    if parameter.min_thickness_railing_mm is None:
        return [f"{len(railing)} Geländer nicht gedruckt: bei {parameter.ruleset_name} gibt es keine Bänder."]
    width = max(1, int(np.ceil(parameter.min_thickness_railing_mm / voxel_grid.pitch - 1e-9)))
    detached = []
    for z, mesh in railing:
        railing_band, lost_ratio = band(mesh, voxel_grid, width)
        if railing_band is None:
            detached.append(f"{z.name or z.guid} ({lost_ratio:.0%} ohne Auflage)")
            continue
        place(voxel_grid, railing_band, z.storey, roof_name(ifc, z, elevations, zones))
    if detached:
        return ["Geländer ohne Gebäude darunter nicht gedruckt: " + ", ".join(detached) + "."]
    return []
