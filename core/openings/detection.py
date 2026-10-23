"""Öffnungen bestimmen: Wirtspaket finden und die Öffnung im Achsensystem des Pakets beschreiben.

Ein Füller (Fenster, Tür, Vorhangfassade) sitzt in einem oder mehreren Wandpaketen (``find_hosts``).
Daraus entsteht je Paket eine ``Opening`` (``opening``): Dickenintervall des Pakets, Spannen von lichter
Öffnung und Füller in den Achsen (Normale n, Breite u, Höhe w). Ohne Paket gilt die eigene Platte
des Füllers, auf die Mindestdicke gebracht. Alle Masse im Modellmassstab [mm].

Eingabe: Füllerpunkte, Öffnungspunkte, Pakete (``Scaling`` mit Box)
Ausgabe: ``Opening`` bzw. die Pakete, in denen ein Füller sitzt
"""

from dataclasses import dataclass

import numpy as np

from config import HOST_MIN_WIDTH_RATIO, HOST_MIN_HEIGHT_RATIO, HOST_PARALLEL_DEG
from core.packages.plates import is_wall, plate
from core.packages.scaling import Scaling

_PARALLEL_COS = np.cos(np.radians(HOST_PARALLEL_DEG))     # Füller liegt in der Ebene des Pakets


@dataclass(frozen=True)
class Opening:
    """Eine Öffnung im eigenen Achsensystem (Zeilen von ``axes``: Normale n, Breite u, Höhe w).

    ``thickness``: Intervall entlang n (gerastetes Paketintervall bzw. eigene Box) und ``voxel``
    seine Voxelzahl. ``clear_span``: u/w-Spannen der sichtbaren Öffnung (Öffnungskörper, sonst
    Füller). ``filling``: u/w-Spannen von Füller und Öffnung zusammen. ``free``: ohne
    Wandpaket – wird nur gesetzt, wenn der Füllkörper das Gebäude berührt.
    """
    kind: str
    axes: np.ndarray
    thickness: tuple[float, float]
    voxel: int
    clear_span: np.ndarray
    filling: np.ndarray
    free: bool = False
    guid: str = ""                 # Füller – für einen eigenen Modus je Fenster/Tür (Ausnahme)

    @property
    def center(self) -> np.ndarray:
        local = [sum(self.thickness) / 2, *self.clear_span.mean(axis=1)]
        return self.axes.T @ np.array(local)


def axis_system(normal_vector: np.ndarray) -> np.ndarray:
    """Rechtshändige Achsen (n, u, w): u waagrecht in der Wand, w nach oben (bei Wänden)."""
    n = np.asarray(normal_vector, dtype=float)
    helper_axis = np.array([0.0, 0.0, 1.0]) if is_wall(n) else np.array([1.0, 0.0, 0.0])
    u = np.cross(helper_axis, n)
    u /= np.linalg.norm(u)
    return np.array([n, u, np.cross(n, u)])


def _spans(points: np.ndarray, axes: np.ndarray) -> np.ndarray:
    p = points @ axes[1:].T
    return np.stack([p.min(axis=0), p.max(axis=0)], axis=1)   # (2, 2): u, w je (lo, hi)


def find_hosts(points: np.ndarray, packages: list[tuple[Scaling, np.ndarray, np.ndarray]],
                 tolerance: float) -> list[tuple[Scaling, np.ndarray]]:
    """Alle Pakete, in deren Box und Dicke ein flächiger Teil der Füllerpunkte liegt.

    Rückgabe je Treffer: (Paket, Maske der Punkte im Paket). Ein Fenster über Eck trifft
    zwei Wandpakete. Fehltreffer (Leibung an einer Querwand oder Gaubenwange, Fenster auf
    einer Decke, Dachfenster am Grat) werden verworfen:
      * Ist der Füller selbst eine Platte, muss sie parallel zum Paket liegen (± 10°).
      * Bei Wänden muss der Teil zudem 20 % der Füllerbreite und die halbe Höhe abdecken.
      * Ein Füller, der keine Platte ist (Fenster über Eck), zählt nur in Wänden.
    """
    own = plate(points)
    hits = []
    for s, lo, hi in packages:
        distance = points @ s.normal_vector
        mask = (np.all((points >= lo - tolerance) & (points <= hi + tolerance), axis=1)
                 & (distance >= s.lo - tolerance) & (distance <= s.hi + tolerance))
        if mask.sum() < 4:                       # nur berührt, nicht im Paket
            continue
        axes = axis_system(s.normal_vector)
        if own is not None and abs(own.normal_vector @ s.normal_vector) < _PARALLEL_COS:
            continue
        if is_wall(s.normal_vector):
            part = points[mask]
            width = np.ptp(part @ axes[1]) / max(np.ptp(points[:, :2], axis=0).max(), 1e-9)
            height = np.ptp(part @ axes[2]) / max(np.ptp(points @ axes[2]), 1e-9)
            if width < HOST_MIN_WIDTH_RATIO or height < HOST_MIN_HEIGHT_RATIO:
                continue
        elif own is None:
            continue
        hits.append((s, mask))
    return hits


def opening(kind: str, points: np.ndarray | None, opening_points: np.ndarray | None,
             host: Scaling | None, min_thickness_mm: float, pitch_mm: float, guid: str = "") -> Opening | None:
    """Öffnung aus Füller- und Öffnungspunkten (Modellmass); None, wenn keine Richtung bestimmbar.

    Ohne ``host`` entsteht eine freie Öffnung: eigene Platte, mindestens ``min_thickness_mm``.
    """
    everything = np.concatenate([p for p in (points, opening_points) if p is not None])
    if host is not None:
        axes = axis_system(host.normal_vector)
        thickness, voxel = (host.lo, host.hi), host.voxel
    else:
        own = plate(everything)
        if own is None:
            return None
        axes = axis_system(own.normal_vector)
        lo, hi = own.span(axes[0])
        voxel = max(int(np.ceil(min_thickness_mm / pitch_mm - 1e-9)), int(np.floor((hi - lo) / pitch_mm + 0.5)))
        center = (lo + hi) / 2
        thickness = (center - voxel * pitch_mm / 2, center + voxel * pitch_mm / 2)
    clear_span = _spans(opening_points if opening_points is not None else points, axes)
    return Opening(kind, axes, thickness, voxel, clear_span, _spans(everything, axes), free=host is None, guid=guid)
