"""Voxel eines einzelnen Bauteils: massgenau, mindestens 1 Voxel dick, verdickt, ohne Öffnungen.

Ablauf je Bauteil (siehe ``core/voxels/shell.voxelize``):
  1. Massgenau voxelisieren (``element_voxel``): Ein Voxel gehört zum Bauteil, wenn sein MITTELPUNKT
     innen liegt. Wo ein Bauteil dünner als ein Voxel ist, kommen die Oberflächen-Voxel dazu.
     Ist das Bauteil nicht geschlossen, gilt der Rückfall: Oberflächen-Voxel + Füllung dünner
     Hohlräume (``fill_cores``).
  2. Verdicken (``thicken``): Dilatation bis zur Mindestwand – nur für Bauteile ausserhalb von Paketen.
  3. Gefälle ausgleichen (``flatten``) und Öffnungen aussparen (``cut_voids``).

Eingabe: Dreiecke eines Bauteils in Voxel-Einheiten (Modell-mm / Pitch)
Ausgabe: Bool-Gitter des Bauteils und sein Ursprung ``lo`` im gemeinsamen Gitter
"""

import numpy as np
import trimesh
from scipy.ndimage import binary_dilation, binary_fill_holes, find_objects, label

from core.voxels.mesh_voxels import frame, inside_voxel, surface_voxel

_NEIGHBORS = np.ones((3, 3, 3), dtype=bool)


def fill_cores(matrix: np.ndarray, max_thickness_voxel: int) -> np.ndarray:
    """Rückfall für offene Körper: füllt Hohlräume, die in ≥ 1 Achse dünn sind (Wandkern).

    binary_fill_holes allein würde auch einen Raum füllen, den eine als Ring
    modellierte Aussenwand umschliesst – darum entscheidet die Form des Hohlraums.
    """
    hollow = binary_fill_holes(matrix) & ~matrix
    if not hollow.any():
        return matrix
    marked, _ = label(hollow)
    thin = [number for number, sl in enumerate(find_objects(marked), start=1)
             if sl is not None and min(s.stop - s.start for s in sl) <= max_thickness_voxel]
    return matrix | np.isin(marked, thin)


def element_voxel(triangles: np.ndarray, max_thickness_voxel: int) -> tuple[np.ndarray, np.ndarray]:
    """Massgenaue Voxel eines Bauteils, mindestens 1 Voxel dick. Rückgabe (Gitter, lo)."""
    lo, size = frame(triangles)
    area = surface_voxel(triangles, lo, size)
    inside = inside_voxel(triangles, lo, size)
    if inside is None:                                        # offener Körper
        return fill_cores(area, max_thickness_voxel), lo
    # Oberflächen-Voxel nur dort, wo kein Innen-Voxel in der Nähe ist (= dünner als 1 Voxel)
    return inside | (area & ~binary_dilation(inside, _NEIGHBORS)), lo


def thicken(matrix: np.ndarray, lo: np.ndarray, voxel: int) -> tuple[np.ndarray, np.ndarray]:
    """Dilatiert ein Bauteil um ``voxel`` Schichten nach allen Seiten (Gitter wächst mit)."""
    if voxel <= 0:
        return matrix, lo
    padded = np.pad(matrix, voxel)
    return binary_dilation(padded, iterations=voxel), lo - voxel


def thickening_voxel(thickness_model_mm: float, min_wall_mm: float, pitch_mm: float) -> int:
    """Wie viele Voxel pro Seite ein Bauteil wachsen muss, um die Mindestwand zu erreichen."""
    if not np.isfinite(thickness_model_mm) or thickness_model_mm >= min_wall_mm:
        return 0
    return int(np.ceil((min_wall_mm - thickness_model_mm) / (2 * pitch_mm)))


def flatten(matrix: np.ndarray) -> np.ndarray:
    """Gefälle ausgleichen: jede belegte Spalte von der tiefsten bis zur höchsten Schicht des Bauteils füllen."""
    k = np.flatnonzero(matrix.any(axis=(0, 1)))
    if not len(k):
        return matrix
    flat = matrix.copy()
    flat[:, :, k[0]:k[-1] + 1] |= matrix.any(axis=2)[:, :, None]
    return flat


def cut_voids(matrix: np.ndarray, lo: np.ndarray, voids: list[trimesh.Trimesh],
              pitch_mm: float) -> tuple[np.ndarray, int]:
    """Leert die Voxel eines Bauteils, deren Mitte in einer seiner Öffnungen liegt.

    Nur dieses Bauteil verliert Voxel: Eine Treppe, die durch das Treppenauge einer Decke läuft,
    bleibt ganz. Rückgabe: (Gitter, Anzahl Öffnungen, die als offener Körper nicht ausschneidbar waren).
    """
    is_open = 0
    for body in voids:
        triangles = body.triangles / pitch_mm
        o_lo, size = frame(triangles)
        mask = inside_voxel(triangles, o_lo, size)
        if mask is None:
            is_open += 1
            continue
        start_idx, stop_idx = np.maximum(o_lo, lo), np.minimum(o_lo + size, lo + matrix.shape)
        if np.any(stop_idx <= start_idx):
            continue
        in_element = tuple(slice(v - x, b - x) for v, b, x in zip(start_idx, stop_idx, lo))
        in_void = tuple(slice(v - x, b - x) for v, b, x in zip(start_idx, stop_idx, o_lo))
        matrix[in_element] &= ~mask[in_void]
    return matrix, is_open
