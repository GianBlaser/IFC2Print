"""Ausrichtung: Modell so drehen, dass die meisten Wände parallel zu X/Y stehen.

Eingabe: Netze der gedruckten Bauteile (main_angle) bzw. IFC-Modell, Massstab und Winkel (model_rotation)
Ausgabe: Hauptwinkel in Grad; 4×4-Drehmatrix um die Grundrissmitte

Ein Voxelgitter ist achsparallel. Schräg stehende Wände werden darin zu Treppen.
Darum wird die Hauptrichtung der senkrechten Flächen im Grundriss bestimmt
(flächengewichtetes Histogramm der Normalenwinkel, modulo 90°) und das Modell vor
dem Voxelisieren um diesen Winkel zurückgedreht. Ein zweites, schräges
Wandsystem bleibt leicht gestuft – gerade wird nur das dominante.
"""

import numpy as np
import trimesh

from core.ifc.model import IfcModel

_BIN_DEG = 0.5          # Auflösung des Histogramms
_REFINE_WINDOW_DEG = 2.0      # Verfeinerung um die Spitze
_MIN_ROTATION_DEG = 0.2  # kleinere Abweichungen werden ignoriert


def main_angle(meshes: list[trimesh.Trimesh]) -> float:
    """Winkel (Grad, −45…45) der dominanten Wandrichtung im Grundriss; 0 = bereits achsparallel."""
    normal_vectors = np.concatenate([m.face_normals for m in meshes]) if meshes else np.zeros((0, 3))
    areas = np.concatenate([m.area_faces for m in meshes]) if meshes else np.zeros(0)
    vertical = np.abs(normal_vectors[:, 2]) < 0.05
    if not vertical.any():
        return 0.0
    angle = np.degrees(np.arctan2(normal_vectors[vertical, 1], normal_vectors[vertical, 0])) % 90
    weight = areas[vertical]
    angle_hist, _ = np.histogram(angle, bins=int(90 / _BIN_DEG), range=(0, 90), weights=weight)
    smoothed = angle_hist + np.roll(angle_hist, 1) + np.roll(angle_hist, -1)   # periodisch (90°)
    peak = (np.argmax(smoothed) + 0.5) * _BIN_DEG
    deviation = (angle - peak + 45) % 90 - 45
    near = np.abs(deviation) <= _REFINE_WINDOW_DEG
    result = (peak + np.average(deviation[near], weights=weight[near]) + 45) % 90 - 45
    return 0.0 if abs(result) < _MIN_ROTATION_DEG else float(result)


def rotation(angle_deg: float, center_xy) -> np.ndarray:
    """4×4-Matrix: dreht um −winkel um die senkrechte Achse durch ``center_xy``."""
    rot_center = np.array([center_xy[0], center_xy[1], 0.0])
    return trimesh.transformations.rotation_matrix(np.radians(-angle_deg), [0, 0, 1], point=rot_center)


def model_rotation(ifc: IfcModel, scale: int, angle: float) -> np.ndarray:
    """Drehmatrix im Modellmass um die Grundrissmitte des Modells."""
    lo, hi = ifc.extent_mm()
    return rotation(angle, (lo[:2] + hi[:2]) / 2 / scale)
