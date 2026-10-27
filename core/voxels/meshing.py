"""Vernetzen: Voxelmatrix → glattes, wasserdichtes Dreiecksnetz.

Marching Cubes macht aus der Bool-Matrix ein geschlossenes Netz. Danach glättet Taubin die
Voxeltreppen, die Quadric-Dezimierung reduziert die Dreiecke, und winzige Schalen
(Vernetzungs-Artefakte) fallen weg.

Eingabe: Bool-Matrix mit Ursprung und Pitch bzw. ein Trimesh
Ausgabe: wasserdichtes Trimesh (Modell-mm)
"""

import numpy as np
import trimesh
import trimesh.smoothing
from skimage import measure

from config import DECIMATION_MAX_VOLUME_CHANGE, DECIMATION_RATIO, SMOOTH_ITERATIONS, SPECK_MIN_VOLUME_MM3


def marching_cubes(matrix: np.ndarray, origin: np.ndarray, pitch: float) -> trimesh.Trimesh:
    """Bool-Matrix oder Feld (Fläche bei 0.5, VoxelGrid.scalar_field) → geschlossenes Dreiecksnetz
    (allseitig gepolstert = immer wasserdicht)."""
    verts, faces, _, _ = measure.marching_cubes(np.pad(matrix, 1).astype(np.float32), level=0.5)
    mesh = trimesh.Trimesh((verts - 1) * pitch + origin, faces, process=False)
    if mesh.volume < 0:   # Marching Cubes liefert konsistente, aber evtl. invertierte Normalen
        mesh.invert()
    return mesh


def postprocessed(mesh: trimesh.Trimesh, specks: bool = True) -> trimesh.Trimesh:
    """Glättet die Voxeltreppen (Taubin) und dezimiert die Dreiecke (Quadric).

    ``specks``: winzige Schalen im fertigen Netz entfernen (``without_specks``). Unnötig – und teuer –,
    wenn das Gitter vorher bereinigt wurde (core/parts/cleanup.without_sliver).

    Die Dezimierung wird nur übernommen, wenn das Mesh dicht bleibt und sein
    Volumen hält – die Nachbearbeitung kann ein druckbares Modell nie verderben.
    Bewusst KEIN fix_normals: es richtet jede Schale nach aussen aus, auch die
    Innenschalen eingeschlossener Räume – die würden dann als Volumen zählen.
    """
    if not len(mesh.faces):
        return mesh
    if SMOOTH_ITERATIONS:
        mesh = mesh.copy()   # Taubin verschiebt nur Punkte → Topologie (Dichtheit) bleibt erhalten
        trimesh.smoothing.filter_taubin(mesh, iterations=SMOOTH_ITERATIONS)
    if DECIMATION_RATIO:
        candidate = decimated(mesh, DECIMATION_RATIO)
        if candidate.is_watertight and abs(candidate.volume - mesh.volume) <= DECIMATION_MAX_VOLUME_CHANGE * abs(mesh.volume):
            mesh = candidate
    return without_specks(mesh) if specks else mesh


def without_specks(mesh: trimesh.Trimesh, min_volume_mm3: float = SPECK_MIN_VOLUME_MM3) -> trimesh.Trimesh:
    """Entfernt winzige geschlossene Schalen (Vernetzungs-Artefakte an diagonalen Voxelkontakten).

    Ganze Schalen fallen weg – die übrigen bleiben unverändert dicht. Eingeschlossene
    Hohlräume (Innenschalen) sind grösser und bleiben erhalten.
    """
    shells = mesh.split(only_watertight=False)
    keep = [s for s in shells if abs(s.volume) >= min_volume_mm3]
    if len(keep) == len(shells) or not keep:
        return mesh
    return trimesh.util.concatenate(keep)


def decimated(mesh: trimesh.Trimesh, fraction: float) -> trimesh.Trimesh:
    """Reduziert das Mesh auf ``fraction`` seiner Dreiecke."""
    target = max(4, int(len(mesh.faces) * fraction))      # ein geschlossener Körper hat mindestens 4 Dreiecke
    if target >= len(mesh.faces):
        return mesh
    candidate = mesh.simplify_quadric_decimation(face_count=target)
    candidate.merge_vertices()
    return candidate
