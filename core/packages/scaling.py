"""Pakete skalieren: ein Paket entlang seiner Normale auf ganze Voxel bringen.

Jedes Paket wird nur entlang seiner Normale affin skaliert: auf ganze Voxel gerundet, mindestens die
Mindestdicke. Länge und Höhe bleiben. Bei achsparalleler Normale liegen die Flächen danach knapp
innerhalb von Voxelgrenzen – gleiche Wandtypen werden überall exakt gleich viele Voxel dick.

Eingabe: Glieder eines Pakets (``Plate``), Mindestdicke und Pitch [mm]
Ausgabe: ``Scaling`` (Matrix, gerastetes Intervall, Voxelzahl) bzw. eine Matrix je Glied
"""

from dataclasses import dataclass

import numpy as np
import trimesh

from core.packages.plates import Plate
from core.packages.thickness import free_standing, interval, thickness

_INSET = 1e-3                                # Anteil eines Voxels, um den gerastete Flächen nach innen rücken


@dataclass(frozen=True)
class Scaling:
    """Ergebnis je Paket im Modellmass: Matrix für alle Glieder und das gerastete Intervall."""
    matrix: np.ndarray
    normal_vector: np.ndarray
    lo: float
    hi: float
    voxel: int            # Dicke in Voxeln (bei schräger Normale gerundet)
    thickened: bool        # True, wenn das Paket für die Mindestdicke wachsen musste


def scaling(plates: list[Plate], min_thickness_mm: float, pitch_mm: float) -> Scaling:
    """Affine Abbildung, die ein Paket (Modellmass) entlang seiner Normale auf die Zieldicke bringt.

    Zieldicke = ganze Voxel, gerundet, mindestens ``min_thickness_mm``. Achsparallele
    Pakete werden zusätzlich so verschoben, dass beide Flächen knapp innerhalb von
    Voxelgrenzen liegen (Voxelmitten liegen auf ganzzahligen Vielfachen des Pitch):
    dann trifft die Voxelisierung exakt ``voxel`` Schichten, egal wo die Wand steht.
    """
    normal_vector = plates[0].normal_vector
    lo, hi = interval(plates)
    old = hi - lo
    center = (lo + hi) / 2
    rounded = int(np.floor(old / pitch_mm + 0.5 + 1e-6))     # Gleichstand → dicker
    voxel = max(int(np.ceil(min_thickness_mm / pitch_mm - 1e-9)), rounded)
    if np.isclose(np.abs(normal_vector).max(), 1.0):                 # achsparallel → rasten
        new = (voxel - 2 * _INSET) * pitch_mm
        if voxel % 2:
            new_center = np.round(center / pitch_mm) * pitch_mm
        else:
            new_center = (np.floor(center / pitch_mm) + 0.5) * pitch_mm
    else:                                                      # schräg: nur Mindestdicke sichern
        new = max(old, min_thickness_mm)
        new_center = center
    factor = new / old if old > 0 else 1.0
    matrix = np.eye(4)
    if old > 0:
        matrix[:3, :3] += (factor - 1) * np.outer(normal_vector, normal_vector)
        matrix[:3, 3] = normal_vector * (new_center - factor * center)
    return Scaling(matrix, normal_vector, new_center - new / 2, new_center + new / 2, voxel,
                      thickened=old < min_thickness_mm)


def members_matrices(plates: list[Plate], package: Scaling, min_thickness_mm: float,
                     pitch_mm: float) -> list[np.ndarray]:
    """Matrix je Glied: die des Pakets; ein freistehendes, danach noch zu dünnes Glied
    wird zusätzlich für sich auf die Mindestdicke gebracht (und gerastet)."""
    matrices = []
    free = free_standing(plates) if len(plates) > 1 else [False]
    for p, alone in zip(plates, free):
        matrix = package.matrix
        if alone:
            scaled = Plate(p.axes, trimesh.transform_points(p.points, matrix))
            if thickness([scaled]) < min_thickness_mm:
                matrix = scaling([scaled], min_thickness_mm, pitch_mm).matrix @ matrix
        matrices.append(matrix)
    return matrices
