"""Steckverbinder-Geometrie: Zapfen und Taschen als Kegelstümpfe, per Boolean in die Teile gerechnet.

Ein ``Connector`` beschreibt Lage und Mass eines Zapfens an der Fuge. Daraus entsteht je Verbinder
ein Zapfen auf dem unteren Teil (``peg``) und eine Tasche im oberen Teil (``socket``): Der Zapfen
wächst aus der Wandkrone nach oben und verjüngt sich (Kegelstumpf); die Tasche hat ringsum und oben das
Passungsspiel des Druckerprofils als Luft. ``apply_connectors`` rechnet beides auf die fertigen Netze.

Eingabe: Teilnetze (Modell-mm), Verbinderplan, Passungsspiel [mm]
Ausgabe: Kopie der Teile mit Zapfen und Taschen sowie Warnungen
"""

from collections import defaultdict
from dataclasses import dataclass

import manifold3d as m3d
import numpy as np
import trimesh

from config import CONNECTOR_MAX_VOLUME_CHANGE, CYLINDER_SEGMENTS, OVERLAP_MM, PEG_TAPER_DEG

EPS_MM = 0.3          # Schneidkörper ragen so weit über die Fläche hinaus (kein koplanarer Schnitt)


@dataclass
class Connector:
    """Ein Steckverbinder an einer Fuge: Lage, Mass und Form des Zapfens (Modell-mm)."""
    bottom: int                       # Label des Teils mit dem Zapfen
    top: int                        # Label des Teils mit der Tasche
    x: float                         # Modell-mm, Mitte an der Fuge
    y: float
    z_joint: float
    width: float                    # an der Fuge; rund: Durchmesser
    length: float                    # an der Fuge; rund: = breite
    height: float                     # Zapfenhöhe über der Fuge
    angle: float = 0.0              # Richtung der Länge im Grundriss (rad)
    is_round: bool = False


def rectangle_points(x: float, y: float, length: float, width: float, angle: float, n: int = 7) -> np.ndarray:
    """Stützpunkte (n × n) eines gedrehten Rechtecks im Grundriss; n = 7 prüft die Auflage, n = 2 gibt die Ecken."""
    u = np.linspace(-length / 2, length / 2, n)
    v = np.linspace(-width / 2, width / 2, n)
    uu, vv = (g.ravel() for g in np.meshgrid(u, v))
    c, s = np.cos(angle), np.sin(angle)
    return np.column_stack([x + uu * c - vv * s, y + uu * s + vv * c])


def _frustum(v: Connector, z0: float, z1: float, allowance: float, slope_from: float) -> trimesh.Trimesh:
    """Kegel-/Pyramidenstumpf von z0 bis z1; Querschnitt = Zapfen-Fuss + 2·zugabe, ab ``slope_from`` verjüngt."""
    t = np.tan(np.radians(PEG_TAPER_DEG))

    def dimensions(z: float) -> tuple[float, float]:
        inset = 2 * t * max(z - slope_from, 0.0)
        return v.length + 2 * allowance - inset, v.width + 2 * allowance - inset

    if v.is_round:
        profile = [(0.0, z0), (dimensions(z0)[0] / 2, z0), (dimensions(z1)[0] / 2, z1), (0.0, z1)]
        mesh = trimesh.creation.revolve(np.array(profile), sections=CYLINDER_SEGMENTS)
        mesh.apply_translation([v.x, v.y, 0.0])
        return mesh
    points = []
    for z in (z0, z1):
        length, width = dimensions(z)
        points += [(*q, z) for q in rectangle_points(v.x, v.y, length, width, v.angle, n=2)]
    return trimesh.convex.convex_hull(np.array(points))


def peg(v: Connector) -> trimesh.Trimesh:
    """Kegelstumpf auf der Krone: Fussmass an der Fuge, nach oben schmaler."""
    return _frustum(v, v.z_joint - OVERLAP_MM, v.z_joint + v.height, 0.0, v.z_joint)


def socket(v: Connector, clearance: float) -> trimesh.Trimesh:
    """Schneidkörper in der Deckenunterseite: Zapfen + Spiel ringsum (Flanken parallel) und oben."""
    allowance = clearance / np.cos(np.radians(PEG_TAPER_DEG))           # senkrechter Abstand zur Flanke = spiel
    return _frustum(v, v.z_joint - EPS_MM, v.z_joint + v.height + clearance, allowance, v.z_joint)


def _manifold(mesh: trimesh.Trimesh, origin: np.ndarray) -> m3d.Manifold | None:
    raw = m3d.Mesh(vert_properties=(np.asarray(mesh.vertices) - origin).astype(np.float32),
                   tri_verts=np.asarray(mesh.faces, dtype=np.uint32))
    m = m3d.Manifold(raw)
    return m if m.status() == m3d.Error.NoError else None


def _boolean(mesh: trimesh.Trimesh, additions: list[trimesh.Trimesh], cuts: list[trimesh.Trimesh]) -> trimesh.Trimesh | None:
    """Teil + Zapfen − Taschen; None, wenn das Ergebnis nicht dicht oder unplausibel ist."""
    origin = mesh.bounds[0].copy()
    m = _manifold(mesh, origin)
    if m is None:
        return None
    if additions:
        z = _manifold(trimesh.util.concatenate(additions), origin)
        if z is None:
            return None
        m = m + z
    if cuts:
        s = _manifold(trimesh.util.concatenate(cuts), origin)
        if s is None:
            return None
        m = m - s
    raw = m.to_mesh()
    new = trimesh.Trimesh(raw.vert_properties[:, :3].astype(np.float64) + origin, raw.tri_verts, process=False)
    if not new.is_watertight or abs(new.volume - mesh.volume) > CONNECTOR_MAX_VOLUME_CHANGE * abs(mesh.volume):
        return None
    return new


def apply_connectors(parts: dict[str, trimesh.Trimesh], mesh_names: dict[int, str], plan: list[Connector],
                       clearance_mm: float) -> tuple[dict[str, trimesh.Trimesh], list[str]]:
    """Kopie von ``parts`` mit Zapfen (unteres Teil) und Taschen (oberes Teil); Rückfall auf das Original je Teil."""
    additions: dict[int, list] = defaultdict(list)
    cuts: dict[int, list] = defaultdict(list)
    for v in plan:
        additions[v.bottom].append(peg(v))
        cuts[v.top].append(socket(v, clearance_mm))
    result, warnings = dict(parts), []
    for number in sorted(set(additions) | set(cuts)):
        name = mesh_names[number]
        new = _boolean(parts[name], additions[number], cuts[number])
        if new is None:
            warnings.append(f"Steckverbinder an «{name}» nicht eingebaut (Boolean ergab kein dichtes Teil).")
        else:
            result[name] = new
    return result, warnings
