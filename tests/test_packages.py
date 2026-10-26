"""Tests für core/packages/grouping: Platten erkennen, Pakete bilden, konsistent skalieren."""

import numpy as np
import pytest
import trimesh

from core.packages.grouping import group_plates
from core.packages.plates import is_wall, plate, snap
from core.packages.scaling import scaling
from core.packages.thickness import thickness
from core.voxels.grid import BuildingElement
from core.voxels.shell import voxelize


def _box(dimensions, center=(0, 0, 0), rotation_rad=0.0):
    m = trimesh.creation.box(extents=dimensions)
    m.apply_transform(trimesh.transformations.rotation_matrix(rotation_rad, [0, 0, 1]))
    return m.apply_translation(center)


def _wall(x0, thickness_x, length=20.0, height=10.0):
    """Wand in y-Richtung, x von x0 bis x0 + thickness_x."""
    return _box((thickness_x, length, height), (x0 + thickness_x / 2, 0, height / 2))


# --- Platten ---------------------------------------------------------------------

def test_wall_is_plate_with_normal_x():
    p = plate(_wall(0, 0.3).vertices)
    assert p is not None and np.allclose(np.abs(p.normal_vector), [1, 0, 0])
    assert is_wall(p.normal_vector)


def test_slab_has_normal_z():
    p = plate(_box((20, 10, 0.25)).vertices)
    assert np.allclose(np.abs(p.normal_vector), [0, 0, 1]) and not is_wall(p.normal_vector)


def test_pillar_is_not_a_plate():
    assert plate(_box((0.3, 0.3, 3.0)).vertices) is None


def test_snap_only_near_axes():
    fast = np.array([[0.99999, 0.0045, 0], [0.7071, 0.7071, 0], [0, 0, 1]])
    result = snap(fast)
    assert np.array_equal(result[0], [1, 0, 0]) and np.allclose(result[1], fast[1])


# --- Pakete ----------------------------------------------------------------------

def test_layered_wall_becomes_one_package():
    """Beton + Dämmung + 2-cm-Bekleidung (separate Wände) = ein Paket, Dicke = Summe."""
    plates = [plate(m.vertices) for m in (_box((250, 8000, 3000), (125, 0, 1500)),
                                             _box((200, 8000, 3000), (350, 0, 1500)),
                                             _box((20, 8000, 3000), (460, 0, 1500)))]
    assert group_plates(plates, tolerance=10) == [0, 0, 0]
    assert thickness(plates) == pytest.approx(470)


def test_small_slit_is_included_large_one_is_not():
    a = plate(_box((200, 8000, 3000), (100, 0, 1500)).vertices)
    near = plate(_box((20, 8000, 3000), (200 + 30 + 10, 0, 1500)).vertices)     # 30 mm Luft
    far_plate = plate(_box((20, 8000, 3000), (200 + 300 + 10, 0, 1500)).vertices)   # 300 mm Luft
    assert group_plates([a, near, far_plate], tolerance=80) == [0, 0, 1]


def test_vertical_and_end_abutting_walls_separate():
    a = plate(_box((200, 4000, 3000), (0, 0, 1500)).vertices)
    cross_wall = plate(_box((4000, 200, 3000), (2100, 0, 1500)).vertices)       # T-Stoss
    next_plate = plate(_box((200, 4000, 3000), (0, 4000, 1500)).vertices)     # gleiche Flucht, Ende an Ende
    assert len(set(group_plates([a, cross_wall, next_plate], tolerance=10))) == 3


# --- Skalierung ------------------------------------------------------------------

def test_thin_wall_is_pulled_to_min_thickness():
    p = plate(_wall(3.13, 0.75).vertices)
    s = scaling([p], min_thickness_mm=1.2, pitch_mm=0.4)
    assert s.voxel == 3 and s.thickened
    assert s.hi - s.lo == pytest.approx(1.2, abs=1e-2)
    new = trimesh.transform_points(p.points, s.matrix)
    assert np.ptp(new[:, 0]) == pytest.approx(s.hi - s.lo)
    assert np.ptp(new[:, 1]) == pytest.approx(20) and np.ptp(new[:, 2]) == pytest.approx(10)  # Länge/Höhe bleiben


def test_thick_wall_is_only_rounded():
    s = scaling([plate(_wall(0.0, 2.35).vertices)], min_thickness_mm=1.2, pitch_mm=0.4)
    assert s.voxel == 6 and not s.thickened


def test_layers_scale_together():
    """Bekleidung bleibt dünn, wenn das Paket dick genug ist – keine aufgeblasene Aussenwand."""
    plates = [plate(m.vertices) for m in (_wall(0, 1.25), _wall(1.25, 1.0), _wall(2.25, 0.1))]
    s = scaling(plates, min_thickness_mm=1.2, pitch_mm=0.4)
    assert s.voxel == 6
    cladding = trimesh.transform_points(plates[2].points, s.matrix)
    assert np.ptp(cladding[:, 0]) < 0.15


@pytest.mark.parametrize("thickness_mm", [0.6, 0.75, 0.8, 0.9, 1.25, 2.2])
def test_same_thickness_same_voxel_count_at_any_position(thickness_mm):
    """Kern des Aliasing-Fixes: dieselbe Wand an 7 Lagen im Gitter → immer gleich viele Voxel."""
    pitch = 0.4
    number_set = set()
    for x0 in np.linspace(0, pitch, 7):
        wall = _wall(5 + x0, thickness_mm)
        s = scaling([plate(wall.vertices)], min_thickness_mm=1.2, pitch_mm=pitch)
        voxel_grid = voxelize([BuildingElement(wall.copy().apply_transform(s.matrix))], pitch, 200)
        number_set.add(int(voxel_grid.matrix.any(axis=(1, 2)).sum()))
    assert len(number_set) == 1
    assert number_set.pop() == max(3, round(thickness_mm / pitch + 1e-9))


def test_sloped_wall_min_thickness_only():
    p = plate(_box((0.5, 20, 10), (0, 0, 5), rotation_rad=0.5).vertices)
    s = scaling([p], min_thickness_mm=1.2, pitch_mm=0.4)
    assert s.hi - s.lo == pytest.approx(1.2)


def test_short_wall_segment_is_plate():
    """Wandstücke kürzer als 2 × Dicke: Normale aus dem Grundriss, nicht aus der Höhe."""
    fragment = _box((250, 300, 3000), rotation_rad=0.3)
    assert plate(fragment.vertices) is None
    p = plate(fragment.vertices, vertical=True)
    assert p is not None and p.normal_vector[2] == 0
    assert np.ptp(p.span(p.normal_vector)) == pytest.approx(250)


def test_detect_slope():
    from core.packages.plates import has_slope
    flat = _box((20, 10, 0.3))
    inclined = _box((20, 10, 0.3))
    inclined.apply_transform(trimesh.transformations.rotation_matrix(np.radians(2), [0, 1, 0]))
    steep = _box((20, 10, 0.3))
    steep.apply_transform(trimesh.transformations.rotation_matrix(np.radians(11), [0, 1, 0]))
    assert not has_slope(flat, (0.3, 5.0))
    assert has_slope(inclined, (0.3, 5.0))
    assert not has_slope(steep, (0.3, 5.0))          # Mansarde 11°: Dach, kein Gefälle


# --- Mindestdicke je Massstab (ScaleParameters.min_thickness_wall_mm) -------------------------

@pytest.mark.parametrize("scale, real_m, expected_mm", [
    ("1:200", 0.30, 1.6),     # 1.5 mm → 4 Voxel: Originaldicke bleibt (gerundet)
    ("1:200", 0.10, 1.2),     # 0.5 mm → auf die Wand-Mindestdicke 1.2 aufgedickt
    ("1:500", 0.20, 0.8),     # 0.4 mm → 1:500 erlaubt 0.8-mm-Wände
    ("1:500", 0.50, 1.2),     # 1.0 mm → 2.5 Voxel, aufgerundet
])
def test_wall_thickness_per_scale(scale, real_m, expected_mm):
    from core.voxels.elements import min_thickness
    from core.analysis.ruleset import ScaleParameters
    param = ScaleParameters.default(scale)
    p = plate(_wall(0.0, real_m * 1000 / param.denominator).vertices, vertical=True)
    min_required = min_thickness(p.normal_vector, 0.8, param.min_thickness_wall_mm)
    s = scaling([p], min_thickness_mm=min_required, pitch_mm=0.4)
    assert s.voxel * 0.4 == pytest.approx(expected_mm)


def test_1_500_reveal_only_outside():
    """0.8-mm-Wand = 2 Voxel: Laibung (1) + Kern (1) → nur aussen vertieft."""
    from types import SimpleNamespace
    from core.openings.windows import reveal_sides
    from core.analysis.ruleset import ScaleParameters
    param, pitch = ScaleParameters.default("1:500"), 0.4
    depth, inner_core = round(param.reveal_depth_mm / pitch), int(np.ceil(param.min_core_reveal_mm / pitch))
    assert reveal_sides(SimpleNamespace(voxel=2), depth, inner_core, outside=-1) == [-1]
    assert reveal_sides(SimpleNamespace(voxel=3), depth, inner_core, outside=-1) == [1, -1]
