"""Geländer als Band (core/voxels/band.py): steht auf dem Gebäude, folgt dem Grundriss, wächst zur Deckenseite."""

import numpy as np
import trimesh

from core.voxels import band
from core.voxels.grid import VoxelGrid

P = 0.4


def _slab(n: int = 40, thickness: int = 3) -> VoxelGrid:
    """Platte n × n Voxel, Schichten 0..thickness-1; Voxelzentren bei i · P."""
    m = np.zeros((n, n, thickness + 2), dtype=bool)
    m[:, :, :thickness] = True
    return VoxelGrid(m, np.zeros(3), P, floor_plans={"EG": np.ones((n, n), dtype=bool)})


def _pane(x0, y0, x1, y1, z0, z1, thickness=0.02) -> trimesh.Trimesh:
    """Glasgeländer: dünne Scheibe von (x0, y0) nach (x1, y1), z0..z1 (Modell-mm)."""
    length = np.hypot(x1 - x0, y1 - y0)
    s = trimesh.creation.box((length, thickness, z1 - z0))
    s.apply_transform(trimesh.transformations.rotation_matrix(np.arctan2(y1 - y0, x1 - x0), [0, 0, 1]))
    s.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
    return s


def test_railing_band_at_plate_edge_stands_and_is_wide():
    g = _slab()
    margin = 39 * P                                     # letzte Voxelreihe in x
    b, lost_ratio = band.band(_pane(margin, 2, margin, 13, 1.0, 5.0), g, width_voxel=2)
    assert b is not None and lost_ratio == 0.0
    assert set(b.i) == {38, 39}                       # zur Deckenseite verbreitert, nicht nach aussen
    assert (b.k_from == 3).all()                       # direkt auf der Platte (oberste Schicht 2)
    assert b.k_to.max() == round(5.0 / P)
    band.place(g, b, "EG")
    assert g.matrix[39, 20, 3:13].all() and not g.matrix[20, 20, 3:].any()


def test_l_shaped_railing_does_not_fill_the_balcony():
    g = _slab()
    mesh = trimesh.util.concatenate([_pane(2, 2, 12, 2, 1.0, 5.0), _pane(2, 2, 2, 12, 1.0, 5.0)])
    b, _ = band.band(mesh, g, width_voxel=2)
    columns = set(zip(b.i, b.j))
    assert (15, 15) not in columns                    # Innenecke bleibt frei
    assert len(columns) < 2 * 3 * 30                  # zwei Schenkel, je höchstens 2·r+1 = 3 Voxel breit


def test_detached_railing_is_dropped():
    g = _slab()
    b, lost_ratio = band.band(_pane(30, 2, 30, 12, 1.0, 5.0), g, width_voxel=2)   # x = 30 mm > Platte (15.6 mm)
    assert b is None and lost_ratio == 1.0


def test_railing_above_the_grid_extends_it():
    g = _slab()
    height = g.matrix.shape[2]
    b, _ = band.band(_pane(4, 2, 4, 12, 1.0, 8.0), g, width_voxel=2)
    assert g.matrix.shape[2] > height and b.k_to.max() < g.matrix.shape[2]
    band.place(g, b, "EG")
    assert g.matrix[b.i[0], b.j[0], b.k_to.max()]
