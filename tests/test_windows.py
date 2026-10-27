"""Tests für Öffnungen auf dem Voxelgitter (core/openings/windows.py)."""

import numpy as np
import pytest

from core.openings.detection import axis_system, find_hosts, Opening, opening
from core.openings.windows import apply, box_mesh, check_mode, fill_box, OPENING_MODES, reveal_depth
from core.voxels.meshing import marching_cubes
from core.packages.scaling import Scaling
from core.voxels.grid import VoxelGrid

_FORM = (10, 20, 20)                      # Gitter: x Wanddicke, y Länge, z Höhe (Pitch 1, Voxel [i,j,k] bei (i,j,k))
_HOLE = (slice(6, 14), slice(6, 14))      # Loch in y und z: Voxel 6..13


def _boxed(lo, hi) -> np.ndarray:
    """Acht Eckpunkte einer achsparallelen Box."""
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])


def _host(lo=1.5, hi=7.5, voxel=6) -> Scaling:
    return Scaling(np.eye(4), np.array([1.0, 0, 0]), lo, hi, voxel, False)


def _wall(x_from=2, x_to=7, with_hole=True) -> np.ndarray:
    """Wandplatte (x_from..x_to inklusive), optional mit schon eingebautem Loch."""
    matrix = np.zeros(_FORM, dtype=bool)
    matrix[x_from:x_to + 1] = True
    if with_hole:
        matrix[(slice(x_from, x_to + 1), *_HOLE)] = False
    return matrix


def _opening(kind="windows", thickness=(1.5 + 1e-3, 7.5 - 1e-3), voxel=6, u=(5.6, 13.4), w=(5.6, 13.4)) -> Opening:
    spans = np.array([u, w])
    return Opening(kind, axis_system(np.array([1.0, 0, 0])), thickness, voxel, spans, spans)


def _apply(matrix, o, mode, reveal_mm=1.0, min_wall_mm=2.0, core_mm=2.0):
    voxel_grid = VoxelGrid(matrix, np.zeros(3), 1.0)
    n = apply(voxel_grid, [o], {o.kind: mode}, min_wall_mm, reveal_mm, core_mm)
    return voxel_grid.matrix, n


# --- Modus und Achsen -------------------------------------------------------------

def test_modes_are_accepted():
    for mode in OPENING_MODES:
        assert check_mode(mode) == mode
    assert set(OPENING_MODES) == {"geschlossen", "ausgeschnitten", "vertieft"}


def test_unknown_mode():
    with pytest.raises(ValueError):
        check_mode("halboffen")


def test_axis_system_wall():
    axes = axis_system(np.array([1.0, 0, 0]))
    assert np.allclose(axes[0], [1, 0, 0])
    assert np.allclose(axes[1], [0, 1, 0])        # u waagrecht
    assert np.allclose(axes[2], [0, 0, 1])        # w nach oben
    assert np.isclose(np.linalg.det(axes), 1.0)


def test_axis_system_right_handed_also_for_sloped_and_slab():
    slope_normal_vector = np.array([1.0, 1.0, 0]) / np.sqrt(2)
    for normal_vector in (slope_normal_vector, [0, -1.0, 0], [0, 0, 1.0]):
        axes = axis_system(np.array(normal_vector))
        assert np.allclose(axes @ axes.T, np.eye(3))
        assert np.isclose(np.linalg.det(axes), 1.0)
    sloped = axis_system(slope_normal_vector)
    assert np.isclose(sloped[1, 2], 0) and np.allclose(sloped[2], [0, 0, 1])


# --- Öffnung bestimmen ------------------------------------------------------------

def test_opening_with_host_and_opening_points():
    host = _host()
    filler = _boxed([3, 6, 6], [6, 13, 13])
    hole = _boxed([3, 7, 8], [6, 12, 11])
    o = opening("windows", filler, hole, host, 2.0, 1.0)
    assert o.thickness == (host.lo, host.hi) and o.voxel == host.voxel
    assert np.allclose(o.clear_span, [[7, 12], [8, 11]])         # aus den Öffnungspunkten
    assert np.allclose(o.filling, [[6, 13], [6, 13]])       # beide zusammen


def test_opening_with_host_without_opening_points_and_filling_spans_both():
    host = _host()
    filler = _boxed([3, 6, 6], [6, 13, 13])
    o = opening("doors", filler, None, host, 2.0, 1.0)
    assert np.allclose(o.clear_span, [[6, 13], [6, 13]])         # Rückfall: Füllerpunkte
    large = _boxed([3, 5, 6], [6, 15, 13])
    o = opening("doors", filler, large, host, 2.0, 1.0)
    assert np.allclose(o.clear_span, [[5, 15], [6, 13]])
    assert np.allclose(o.filling, [[5, 15], [6, 13]])


def test_opening_without_host_thickness_at_least_min_wall():
    filler = _boxed([3, 0, 0], [4, 20, 10])               # 1 mm dünne Platte, Normale ±x
    o = opening("windows", filler, None, None, 3.0, 1.0)
    assert abs(o.axes[0][0]) == pytest.approx(1.0)
    assert o.voxel == 3
    assert o.thickness[1] - o.thickness[0] == pytest.approx(o.voxel * 1.0) and o.voxel * 1.0 >= 3.0
    assert sum(o.thickness) / 2 == pytest.approx(3.5 * o.axes[0][0])      # um die eigene Mitte
    thick = opening("windows", _boxed([3, 0, 0], [8, 20, 10]), None, None, 3.0, 1.0)
    assert thick.voxel == 5                                    # dicker als Mindestwand: bleibt


def test_opening_without_host_no_plate_like_body():
    assert opening("windows", _boxed([0, 0, 0], [5, 5, 5]), None, None, 2.0, 1.0) is None


# --- Wirte suchen ----------------------------------------------------------------

def _package(normal_vector, lo, hi, box_lo, box_hi):
    return (Scaling(np.eye(4), np.array(normal_vector, dtype=float), lo, hi, 3, False),
            np.array(box_lo, dtype=float), np.array(box_hi, dtype=float))


_WALL_X = _package([1, 0, 0], 0.0, 3.0, [0, 0, 0], [3, 40, 30])          # Wand in y-Richtung
_WALL_Y = _package([0, 1, 0], 0.0, 3.0, [0, 0, 0], [40, 3, 30])          # Wand in x-Richtung, Ecke bei 0/0
_SLAB = _package([0, 0, 1], -3.0, 0.0, [0, 0, -3], [40, 40, 0])


def test_corner_window_hits_both_walls():
    """Ein Fenster über Eck (L-förmig) bekommt in jeder Wand einen eigenen Füllkörper."""
    leg_x = _boxed([1, 1, 5], [2, 15, 20])                         # liegt in _WALL_X
    leg_y = _boxed([1, 1, 5], [12, 2, 20])                         # liegt in _WALL_Y
    points = np.concatenate([leg_x, leg_y])
    hits = find_hosts(points, [_WALL_X, _WALL_Y], tolerance=0.5)
    assert len(hits) == 2
    for (s, mask), leg in zip(hits, (leg_x, leg_y)):
        assert np.ptp(points[mask] @ np.cross([0, 0, 1.0], s.normal_vector)) == pytest.approx(
            np.ptp(leg @ np.cross([0, 0, 1.0], s.normal_vector)), abs=1.5)


def test_window_on_slab_and_at_cross_wall_has_no_host():
    """Unterkante auf der Decke bzw. Leibung an einer Querwand sind keine Wirte."""
    windows = _boxed([10, 1, 0], [20, 2, 20])                           # sitzt nur in _WALL_Y
    hits = find_hosts(windows, [_WALL_Y, _SLAB, _package([1, 0, 0], 20.0, 23.0, [20, 0, 0], [23, 40, 30])], 0.5)
    assert [s.normal_vector.tolist() for s, _ in hits] == [[0, 1, 0]]


def test_roof_window_in_roof_plane():
    roof = _package([0, 0, 1], 9.0, 11.0, [0, 0, 9], [40, 40, 11])
    velux = _boxed([5, 5, 9.2], [8, 10, 10.6])                          # flach in der Dachebene
    assert len(find_hosts(velux, [roof], 0.5)) == 1


# --- Körper -----------------------------------------------------------------------

def test_box_bounds_match_the_spans():
    spans = [(0, 2), (1, 4), (-1, 3)]
    k = box_mesh(np.eye(3), spans)
    assert np.allclose(k.bounds, [[0, 1, -1], [2, 4, 3]])
    assert k.is_watertight and k.volume == pytest.approx(2 * 3 * 4)


def test_box_in_rotated_system():
    k = box_mesh(axis_system(np.array([0.0, 1.0, 0])), [(10, 12), (0, 3), (0, 4)])
    assert k.is_watertight and k.volume == pytest.approx(24)
    assert np.isclose(k.bounds[0][1], 10) and np.isclose(k.bounds[1][1], 12)    # Dicke entlang n = y


# --- Laibungstiefe ---------------------------------------------------------------

@pytest.mark.parametrize("voxel, expected", [
    (3, 0.2),        # 1.2-mm-Wand: je 0.2 mm, Kern 0.8 mm
    (4, 0.35),       # 1.6 mm: (1.6 − 0.8) / 2 = 0.4 → höchstens 0.35
    (5, 0.35),
    (2, 0.0),        # 0.8 mm: keine Laibung, die Öffnung bleibt voll
])
def test_reveal_depth_both_sides_between_min_and_max(voxel, expected):
    assert reveal_depth(_opening(voxel=voxel), 0.4, 0.35, 0.8) == pytest.approx(expected)


def test_reveal_depth_below_minimum_stays_full():
    """1.4 mm Kern in 1.6-mm-Wand liesse je 0.1 mm – unter REVEAL_MIN_DEPTH_MM."""
    assert reveal_depth(_opening(voxel=4), 0.4, 0.35, 1.4) == 0.0


def test_core_never_thinner_than_min_wall():
    """Der Kern hält auch die Mindestwand des Profils ein, wenn der Mindestkern kleiner ist: 6 Voxel, Tiefe 2,
    Mindestwand 3 → je 1.5 Voxel Laibung, Kern 3."""
    matrix, _ = _apply(_wall(), _opening(), "vertieft", reveal_mm=2.0, min_wall_mm=3.0, core_mm=1.0)
    assert matrix[3:7, 6:14, 6:14].all() and not matrix[[2, 7], 6:14, 6:14].any()


# --- Anwenden ---------------------------------------------------------------------

def test_closed_fills_the_hole_over_the_whole_thickness():
    matrix, n = _apply(_wall(), _opening(), "geschlossen")
    assert np.array_equal(matrix, _wall(with_hole=False))
    assert matrix[2:8, 6:14, 6:14].all()
    assert n == 1


def test_unknown_variant_is_closed_and_mode_is_checked():
    o = _opening(kind="sonst")
    voxel_grid = VoxelGrid(_wall(), np.zeros(3), 1.0)
    assert apply(voxel_grid, [o], {}, 2.0, 1.0) == 1
    assert np.array_equal(voxel_grid.matrix, _wall(with_hole=False))
    with pytest.raises(ValueError):
        apply(voxel_grid, [o], {"sonst": "halboffen"}, 2.0, 1.0)


def test_recessed_leaves_one_voxel_layer_empty_on_both_sides():
    matrix, n = _apply(_wall(), _opening(), "vertieft")
    expected = _wall(with_hole=False)
    expected[(2, *_HOLE)] = False
    expected[(7, *_HOLE)] = False
    assert np.array_equal(matrix, expected)
    assert matrix[3:7, 6:14, 6:14].all() and not matrix[2, 6:14, 6:14].any() and not matrix[7, 6:14, 6:14].any()
    assert n == 1


@pytest.mark.parametrize("x_to, face_depth", [(4, 0.2), (6, 0.35)])
def test_recess_finer_than_a_voxel(x_to, face_depth):
    """Pitch 0.4 mm: Die Laibung liegt im Netz je Seite 0.2 mm (1.2-mm-Wand) bzw. 0.35 mm (2.0 mm) tief,
    obwohl ein Voxel 0.4 mm misst. Wand x = 2..x_to, Flächen bei 0.6 und (x_to + 0.5) · 0.4."""
    p, voxel = 0.4, x_to - 1
    lo, hi = 1.5 * p, (x_to + 0.5) * p
    span = np.array([(5.5 * p, 13.5 * p), (5.5 * p, 13.5 * p)])
    o = Opening("windows", axis_system(np.array([1.0, 0, 0])), (lo, hi), voxel, span, span)
    voxel_grid = VoxelGrid(_wall(2, x_to), np.zeros(3), p)
    assert apply(voxel_grid, [o], {"windows": "vertieft"}, 0.8, 0.35, 0.8) == 1
    mesh = marching_cubes(voxel_grid.scalar_field(voxel_grid.matrix, np.zeros(3, dtype=int)), voxel_grid.origin, p)
    middle = np.all(np.abs(mesh.vertices[:, 1:] - 9.5 * p) < 2 * p, axis=1)       # Mitte der Öffnung
    x = np.unique(np.round(mesh.vertices[middle, 0], 3))
    assert x == pytest.approx([lo + face_depth, hi - face_depth], abs=2e-3)


def test_recess_too_thin_wall_stays_full():
    """2-Voxel-Wand bei Mindestkern 2: keine Laibung, die Öffnung wird nur gefüllt."""
    o = _opening(thickness=(1.5 + 1e-3, 3.5 - 1e-3), voxel=2)
    matrix, _ = _apply(_wall(2, 3), o, "vertieft")
    assert np.array_equal(matrix, _wall(2, 3, with_hole=False))


def test_refilled_voxel_ignores_stored_level():
    """Wird ein Laibungsvoxel später wieder gefüllt, gilt die Bool-Matrix, nicht der gespeicherte Feldwert."""
    voxel_grid = VoxelGrid(_wall(), np.zeros(3), 1.0)
    apply(voxel_grid, [_opening()], {"windows": "vertieft"}, 2.0, 1.0, 2.0)
    voxel_grid.matrix[2, 6:14, 6:14] = True
    field = voxel_grid.scalar_field(voxel_grid.matrix, np.zeros(3, dtype=int))
    assert (field[2, 6:14, 6:14] == 1).all() and (field[7, 6:14, 6:14] < 0.5).all()


def test_free_opening_only_with_contact():
    """Loggia-Fenster ohne Wand: gefüllt, wenn es ans Gebäude stösst – sonst nicht."""
    empty = np.zeros(_FORM, dtype=bool)
    empty[:, :, :6] = True                                       # «Decke» bis z = 5
    o = Opening("windows", axis_system(np.array([1.0, 0, 0])), (2.5, 5.5), 3,
                 np.array([(6.6, 12.4), (6.6, 12.4)]), np.array([(6.6, 12.4), (6.6, 12.4)]), free=True)
    voxel_grid = VoxelGrid(empty.copy(), np.zeros(3), 1.0)
    assert apply(voxel_grid, [o], {"windows": "geschlossen"}, 2.0, 1.0) == 1
    assert voxel_grid.matrix[3:6, 7:13, 7:13].all()
    far = Opening("windows", o.axes, o.thickness, 3, np.array([(6.6, 12.4), (12.6, 17.4)]),
                    np.array([(6.6, 12.4), (12.6, 17.4)]), free=True)    # schwebt über der «Decke»
    voxel_grid = VoxelGrid(empty.copy(), np.zeros(3), 1.0)
    assert apply(voxel_grid, [far], {"windows": "geschlossen"}, 2.0, 1.0, np.zeros(3)) == 0
    assert np.array_equal(voxel_grid.matrix, empty)


def test_cut_out_cuts_through_all_layers():
    matrix, n = _apply(_wall(with_hole=False), _opening(), "ausgeschnitten")
    assert np.array_equal(matrix, _wall(with_hole=True))
    assert not matrix[:, 6:14, 6:14].any()
    assert n == 1


def test_too_small_opening_is_only_filled():
    for u, w in (((7.6, 10.4), (5.6, 13.4)), ((5.6, 13.4), (7.6, 10.4))):     # Breite bzw. Höhe 2.8 < 4
        o = _opening(u=u, w=w)
        full = _wall(with_hole=False)
        matrix, n = _apply(full.copy(), o, "ausgeschnitten")
        assert np.array_equal(matrix, full) and n == 0               # nichts ausgeschnitten
        with_hole = full.copy()
        with_hole[2:8, round(u[0]):round(u[1]) + 1, round(w[0]):round(w[1]) + 1] = False
        filled, n = _apply(with_hole, o, "ausgeschnitten")
        assert np.array_equal(filled, full) and n == 1             # Loch in der Wand wird gefüllt


def test_return_value_counts_only_changed_openings():
    voxel_grid = VoxelGrid(_wall(), np.zeros(3), 1.0)
    already_full = _opening(kind="doors", u=(0.6, 3.4), w=(0.6, 3.4))   # liegt im bereits vollen Wandteil
    n = apply(voxel_grid, [_opening(), already_full], {}, 2.0, 1.0)
    assert n == 1


# --- Füllquader -------------------------------------------------------------------

def test_fill_box_thinnest_axis_becomes_min_wall_and_stays_centered():
    k = fill_box([0, 0, 0], [20, 0.5, 30], 0.8)
    assert np.allclose(k.extents, [20, 0.8, 30])
    assert np.allclose(k.bounds.mean(axis=0), [10, 0.25, 15])
    assert k.is_watertight and k.volume > 0


def test_fill_box_thicker_axis_stays_and_other_axes_unchanged():
    k = fill_box([5, 0, 10], [7, 20, 40], 0.8)
    assert np.allclose(k.extents, [2, 20, 30])
    assert np.allclose(k.bounds, [[5, 0, 10], [7, 20, 40]])
