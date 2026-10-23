"""Netz → Voxel: Oberflächen-Voxel und Innen-Voxel eines Dreiecksnetzes.

Zwei Arten, ein Netz in ein Voxelraster zu legen:
  * ``surface_voxel``: alle Voxel, die eine Fläche berührt (auch bei Teilen dünner als ein Voxel).
  * ``inside_voxel``: Voxel, deren MITTELPUNKT im geschlossenen Körper liegt (Windungszahl je Gitterspalte).
Alle Koordinaten sind Voxel-Einheiten (Modell-mm / Pitch).

Eingabe: Dreiecke (F, 3, 3) in Voxel-Einheiten, Ursprung ``lo`` und Grösse ``size`` des lokalen Gitters
Ausgabe: Bool-Gitter der Form ``size`` (``inside_voxel``: None, wenn der Körper offen ist)
"""

from dataclasses import dataclass

import numpy as np

_POINTS_PER_BLOCK = 1_000_000   # Speicherbremse beim Abtasten grosser Dreiecke
_CROSSINGS_PER_BLOCK = 4_000_000   # Speicherbremse: so viele Strahl-Kandidaten je Block
# Strahlen laufen minim neben den Voxelmitten durch, damit sie nie exakt eine
# Dreieckskante oder Ecke treffen (sonst würde ein Schnittpunkt doppelt gezählt).
_RAY_OFFSET = np.array([1.234567e-4, 2.345678e-4])


def frame(triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(lo, Grösse) des lokalen Gitters, das alle Voxel eines Bauteils fasst (Voxel-Einheiten)."""
    points = triangles.reshape(-1, 3)
    if not len(points) or not np.isfinite(points).all():
        raise ValueError("Netz ohne Punkte oder mit nicht endlichen Koordinaten")
    lo = np.rint(points.min(axis=0)).astype(np.int64)
    return lo, np.rint(points.max(axis=0)).astype(np.int64) - lo + 1


def surface_voxel(triangles: np.ndarray, lo: np.ndarray, size: np.ndarray) -> np.ndarray:
    """Alle Voxel, die eine Fläche des Bauteils berührt (Punktraster ≤ ½ Voxel je Dreieck).

    ``triangles``: (F, 3, 3) in Voxel-Einheiten (Koordinate / Pitch).
    """
    voxel_grid = np.zeros(tuple(size), dtype=bool)
    edge_len = np.linalg.norm(triangles - np.roll(triangles, 1, axis=1), axis=2).max(axis=1)
    partition = np.maximum(1, np.ceil(edge_len * 2).astype(np.int64))     # Punktabstand ≤ ½ Voxel
    for n in np.unique(partition):
        i, j = np.mgrid[0:n + 1, 0:n + 1]
        inside = i + j <= n
        a, b = i[inside] / n, j[inside] / n
        bary_weights = np.stack([1 - a - b, a, b], axis=1)              # (P, 3) baryzentrisch
        selection = triangles[partition == n]
        step = max(1, _POINTS_PER_BLOCK // len(bary_weights))
        for s in range(0, len(selection), step):
            p = np.einsum("pk,tkd->tpd", bary_weights, selection[s:s + step]).reshape(-1, 3)
            idx = np.clip(np.rint(p).astype(np.int64) - lo, 0, size - 1)
            voxel_grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return voxel_grid


def inside_voxel(triangles: np.ndarray, lo: np.ndarray, size: np.ndarray) -> np.ndarray | None:
    """Voxel, deren Mittelpunkt im Körper liegt (Windungszahl entlang Z-Strahlen).

    Je Gitterspalte (i, j) zählt jeder Durchstoss eines Dreiecks +1 (Fläche zeigt nach
    unten = Eintritt) oder −1 (nach oben = Austritt). Ein Voxel ist innen, wenn die
    Summe der Durchstösse darunter ≠ 0 ist. Das ist robust bei überlappenden Teilkörpern
    eines Bauteils. Bleibt oben ein Rest ≠ 0, ist der Körper offen → Rückgabe None.
    """
    rays = _rays_through_triangles(triangles, lo, size)
    tally = np.zeros((size[0], size[1], size[2] + 1), dtype=np.int32)
    boundaries = np.searchsorted(np.cumsum(rays.count), np.arange(_CROSSINGS_PER_BLOCK, rays.count.sum() + 1, _CROSSINGS_PER_BLOCK), side="right")
    for t0, t1 in zip(np.r_[0, boundaries], np.r_[boundaries, len(rays.count)]):
        _add_crossings(tally, rays, t0, t1)
    winding = np.cumsum(tally, axis=2)
    if winding[:, :, -1].any():
        return None
    return winding[:, :, :-1] != 0


@dataclass
class _Rays:
    """Die Dreiecke, die ein Z-Strahl treffen kann, und die Gitterspalten (i, j), die jedes überdeckt."""
    a: np.ndarray             # (T, 3) erster Eckpunkt
    v0: np.ndarray            # (T, 3) Kante a → b
    v1: np.ndarray            # (T, 3) Kante a → c
    denominator: np.ndarray   # (T,) 2 × Fläche im Grundriss, Vorzeichen = Normale z
    i0: np.ndarray            # erste Spalte in i
    j0: np.ndarray            # erste Spalte in j
    nj: np.ndarray            # Anzahl Spalten in j
    count: np.ndarray         # Anzahl Spalten (Strahlen-Kandidaten) je Dreieck


def _rays_through_triangles(triangles: np.ndarray, lo: np.ndarray, size: np.ndarray) -> _Rays:
    """Senkrechte Dreiecke ausscheiden und je Dreieck die Spalten bestimmen, deren Strahl es treffen kann."""
    tri = triangles - lo                                      # Voxelmitten liegen auf ganzen Zahlen
    tri[:, :, :2] -= _RAY_OFFSET
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    v0, v1 = b - a, c - a
    denominator = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]       # 2 × Fläche im Grundriss, Vorzeichen = Normale z
    visible = np.abs(denominator) > 1e-12                       # senkrechte Dreiecke treffen keinen Z-Strahl
    a, v0, v1, denominator = a[visible], v0[visible], v1[visible], denominator[visible]
    xy = tri[visible][:, :, :2]
    i0 = np.clip(np.ceil(xy[:, :, 0].min(axis=1)).astype(np.int64), 0, size[0])
    i1 = np.clip(np.floor(xy[:, :, 0].max(axis=1)).astype(np.int64), -1, size[0] - 1)
    j0 = np.clip(np.ceil(xy[:, :, 1].min(axis=1)).astype(np.int64), 0, size[1])
    j1 = np.clip(np.floor(xy[:, :, 1].max(axis=1)).astype(np.int64), -1, size[1] - 1)
    nj = np.maximum(0, j1 - j0 + 1)
    count = np.maximum(0, i1 - i0 + 1) * nj
    return _Rays(a, v0, v1, denominator, i0, j0, nj, count)


def _add_crossings(tally: np.ndarray, rays: _Rays, t0: int, t1: int) -> None:
    """Zählt die Durchstösse der Dreiecke t0 … t1 ins ``tally`` (+1 Eintritt, −1 Austritt, am ersten Voxel darüber)."""
    n = rays.count[t0:t1]
    if not n.sum():
        return
    a, v0, v1, denominator = rays.a, rays.v0, rays.v1, rays.denominator
    t = np.repeat(np.arange(t0, t1), n)                    # Dreieck je Kandidat
    k = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)  # laufende Nummer im Dreieck
    i = rays.i0[t] + k // rays.nj[t]
    j = rays.j0[t] + k % rays.nj[t]
    px, py = i - a[t, 0], j - a[t, 1]
    u = (px * v1[t, 1] - v1[t, 0] * py) / denominator[t]
    v = (v0[t, 0] * py - px * v0[t, 1]) / denominator[t]
    hits = (u >= 0) & (v >= 0) & (u + v <= 1)
    t, i, j, u, v = t[hits], i[hits], j[hits], u[hits], v[hits]
    z = a[t, 2] + u * v0[t, 2] + v * v1[t, 2]
    k_first = np.clip(np.floor(z).astype(np.int64) + 1, 0, tally.shape[2] - 1)   # erster Voxel über dem Durchstoss
    np.add.at(tally, (i, j, k_first), np.where(denominator[t] < 0, 1, -1))
