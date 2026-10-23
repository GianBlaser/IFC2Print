"""Plattenartige Bauteile erkennen: Dickenrichtung (Normale), Flächenrichtungen, Gefälle.

Wände, Decken, Dächer und Bekleidungen sind Platten: eine Kante (die Dicke) ist deutlich kleiner als die
beiden anderen. Über die orientierte Box erhält jede Platte ihre Achsen (Zeilen: Normale, dann zwei
Flächenrichtungen). Nahezu achsparallele Richtungen werden exakt auf ±x/±y/±z eingerastet (``snap``).
Wände (``vertical``) haben ihre Normale immer im Grundriss.

Eingabe: Punkte eines Bauteils (reale oder Modell-mm)
Ausgabe: ``Plate`` (Achsen und Punkte) oder None, wenn das Bauteil nicht plattenartig ist
"""

from dataclasses import dataclass

import numpy as np
import trimesh

from config import (PLATE_AXIS_SNAP_DEG, PLATE_MAX_THICKNESS_RATIO, SLOPE_MIN_AREA_RATIO, TOP_MIN_NORMAL_Z,
                    WALL_MAX_NORMAL_Z)

# Klassen, deren Bauteile Pakete bilden können (Präfix, damit IfcWallStandardCase u.ä. mitzählen)
PLATE_CLASSES = ("IfcWall", "IfcSlab", "IfcRoof", "IfcCovering", "IfcPlate", "IfcBuildingElementPart")
_AXIS_COS = np.cos(np.radians(PLATE_AXIS_SNAP_DEG))        # Achse wird auf x/y/z eingerastet


@dataclass(frozen=True)
class Plate:
    """Plattenartiges Bauteil: Achsen (Zeilen: Normale, dann zwei Flächenrichtungen) und Punkte."""
    axes: np.ndarray
    points: np.ndarray

    @property
    def normal_vector(self) -> np.ndarray:
        return self.axes[0]

    def span(self, direction: np.ndarray) -> tuple[float, float]:
        p = self.points @ direction
        return float(p.min()), float(p.max())

    def in_model(self, points: np.ndarray, transform: np.ndarray) -> "Plate":
        """Dieselbe Platte im Modellmass: neue Punkte, Achsen mitgedreht (``transform`` 4×4)."""
        return Plate(snap(self.axes @ transform[:3, :3].T), points)


def snap(axes: np.ndarray) -> np.ndarray:
    """Setzt nahezu achsparallele Richtungen exakt auf ±x/±y/±z."""
    axes = np.array(axes, dtype=float)
    for row in axes:
        k = int(np.argmax(np.abs(row)))
        if abs(row[k]) >= _AXIS_COS:
            sign_value = np.sign(row[k])
            row[:] = 0.0
            row[k] = sign_value
    return axes


def plate(points: np.ndarray, vertical: bool = False) -> Plate | None:
    """Platte aus den Punkten eines Bauteils; None, wenn es nicht plattenartig ist.

    ``vertical`` (Wände): Die Normale liegt immer im Grundriss und ist die kürzere Kante
    der kleinsten Grundriss-Box – auch kurze Wandstücke (Länge < 2 × Dicke) zählen dann.
    """
    if len(points) < 4:                       # weniger Punkte spannen keine Box auf
        return None
    if vertical:
        return _wall(points)
    try:
        to_origin, edges = trimesh.bounds.oriented_bounds(points)
    except Exception:  # degenerierte Punktwolke
        return None
    order = np.argsort(edges)
    if edges[order[1]] <= 0 or edges[order[0]] > PLATE_MAX_THICKNESS_RATIO * edges[order[1]]:
        return None
    # Zeilen der Rotation = Richtungen der Box-Kanten im Weltsystem
    return Plate(snap(to_origin[:3, :3][order]), points)


def _wall(points: np.ndarray) -> Plate | None:
    try:
        to_origin, edges = trimesh.bounds.oriented_bounds_2D(points[:, :2])
    except Exception:  # alle Punkte auf einer Linie
        return None
    if np.ptp(points[:, 2]) <= 0 or edges.min() <= 0:
        return None
    k = int(np.argmin(edges))
    normal_vector = np.array([*to_origin[k, :2], 0.0])          # Zeile k der 2D-Rotation
    normal_vector /= np.linalg.norm(normal_vector)
    lengthwise = np.array([-normal_vector[1], normal_vector[0], 0.0])
    return Plate(snap(np.array([normal_vector, lengthwise, [0.0, 0.0, 1.0]])), points)


def is_wall(normal_vector: np.ndarray) -> bool:
    """Senkrechte Platte (Normale liegt im Grundriss)."""
    return abs(float(normal_vector[2])) < WALL_MAX_NORMAL_Z


def has_slope(mesh: trimesh.Trimesh, deg: tuple[float, float]) -> bool:
    """True, wenn die nach oben zeigende Fläche überwiegend flach geneigt ist (Entwässerungsgefälle).

    Massgebend ist der Flächenanteil der Oberseite mit einer Neigung zwischen ``deg[0]`` und
    ``deg[1]``. Ebene Decken (0°), Absätze und steile Dächer zählen nicht.
    """
    normal_vectors, areas = mesh.face_normals, mesh.area_faces
    top = normal_vectors[:, 2] > TOP_MIN_NORMAL_Z
    if not top.any() or areas[top].sum() <= 0:
        return False
    inclination = np.degrees(np.arccos(np.clip(normal_vectors[top, 2], -1, 1)))
    inclined = (inclination >= deg[0]) & (inclination <= deg[1])
    return bool(areas[top][inclined].sum() >= SLOPE_MIN_AREA_RATIO * areas[top].sum())
