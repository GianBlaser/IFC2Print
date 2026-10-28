"""Tests für core/voxels/shell: massgenaue Voxel, Rückfall, Verdicken, Gitteroperationen, Vernetzung."""

import numpy as np
import pytest
import trimesh

from core.voxels.element_voxels import element_voxel, fill_cores, flatten, thicken, thickening_voxel
from core.voxels.grid import BuildingElement, Owner, VoxelGrid
from core.voxels.mesh_voxels import frame, inside_voxel, surface_voxel
from core.voxels.shell import close_gaps, voxelize


def _shell(n=20):
    m = np.zeros((n, n, n), dtype=bool)
    m[0], m[-1], m[:, 0], m[:, -1], m[:, :, 0], m[:, :, -1] = (True,) * 6
    return m


def _box(dimensions, center=(0, 0, 0), rotation_rad=0.0):
    m = trimesh.creation.box(extents=dimensions)
    m.apply_transform(trimesh.transformations.rotation_matrix(rotation_rad, [0, 0, 1]))
    return m.apply_translation(center)


# --- Massgenaue Voxel -----------------------------------------------------------

@pytest.mark.parametrize("rotation", [0.0, 0.4, 1.1])
def test_inside_voxel_matches_the_volume(rotation):
    """Auch schräg gedreht: Voxelzahl ≈ exaktes Volumen (kein ½-Voxel-Aufschlag mehr)."""
    body = _box((10, 10, 10), (5.3, 7.1, 3.2), rotation)
    voxel_grid, _ = element_voxel(body.triangles, max_thickness_voxel=9)
    assert voxel_grid.sum() == pytest.approx(body.volume, rel=0.03)


def test_overlapping_sub_bodies_and_room():
    """Vier überlappende Wände um einen Raum: Vereinigung wird gezählt, der Raum bleibt leer."""
    ring = trimesh.util.concatenate([_box(e, t) for e, t in [
        ((30, 2, 10), (0, 14, 5)), ((30, 2, 10), (0, -14, 5)), ((2, 30, 10), (14, 0, 5)), ((2, 30, 10), (-14, 0, 5))]])
    lo, size = frame(ring.triangles)
    inside = inside_voxel(ring.triangles, lo, size)
    assert inside.sum() == 2 * 600 + 2 * 520
    assert not inside[3:-3, 3:-3, :].any()


def test_solid_block_becomes_full():
    """Früher blieben Bauteile, die in allen Achsen > 0.75 m messen, innen hohl."""
    block = _box((40, 40, 40), (20, 20, 20))
    voxel_grid, _ = element_voxel(block.triangles, max_thickness_voxel=3)
    assert voxel_grid[5:-5, 5:-5, 5:-5].all()


def test_open_body_uses_fallback():
    is_open = _box((10, 10, 10))
    is_open.faces = is_open.faces[is_open.face_normals[:, 2] < 0.5]              # Deckel fehlt
    lo, size = frame(is_open.triangles)
    assert inside_voxel(is_open.triangles, lo, size) is None
    voxel_grid, _ = element_voxel(is_open.triangles, max_thickness_voxel=9)
    assert voxel_grid.any()


def test_thin_plate_keeps_at_least_one_voxel():
    """0.3 Voxel dick: kein Mittelpunkt liegt innen, trotzdem verschwindet die Platte nicht."""
    plate = _box((20, 20, 0.3), (0, 0, 0.1))
    voxel_grid, _ = element_voxel(plate.triangles, max_thickness_voxel=9)
    covered = voxel_grid.any(axis=2)
    assert covered[2:-2, 2:-2].all()


def test_surface_of_a_cube():
    cube = trimesh.creation.box(extents=(10, 10, 10))
    lo, size = frame(cube.triangles)
    voxel_grid = surface_voxel(cube.triangles, lo, size)
    assert voxel_grid.shape == (11, 11, 11) and tuple(lo) == (-5, -5, -5)
    assert voxel_grid[0].all() and voxel_grid[-1].all() and voxel_grid[:, :, 0].all()
    assert not voxel_grid[2:-2, 2:-2, 2:-2].any()


def test_large_triangle_without_gaps():
    triangle = np.array([[[0, 0, 0], [200, 0, 0], [0, 200, 0]]], dtype=float)
    lo, size = frame(triangle)
    voxel_grid = surface_voxel(triangle, lo, size)
    i, j = np.mgrid[0:201, 0:201]
    assert voxel_grid[:, :, 0][i + j <= 199].all()


# --- Rückfall: Kernfüllung nach Form --------------------------------------------

def test_small_cavity_is_filled():
    m = np.ones((3, 3, 3), dtype=bool)
    m[1, 1, 1] = False
    assert fill_cores(m, max_thickness_voxel=1).all()


def test_large_room_stays_hollow():
    assert not fill_cores(_shell(), max_thickness_voxel=3)[1:-1, 1:-1, 1:-1].any()


def test_without_cavity_unchanged():
    m = np.zeros((4, 4, 4), dtype=bool)
    m[0, 0, 0] = True
    assert np.array_equal(fill_cores(m, 5), m)


# --- Verdicken ----------------------------------------------------------------

@pytest.mark.parametrize("thickness, expected", [(0.8, 0), (1.5, 0), (0.4, 1), (0.1, 1), (0.0, 1), (float("nan"), 0)])
def test_thickening_voxel(thickness, expected):
    assert thickening_voxel(thickness, min_wall_mm=0.8, pitch_mm=0.4) == expected


def test_thicken_grows_on_all_sides():
    m = np.zeros((1, 1, 1), dtype=bool)
    m[0, 0, 0] = True
    new, lo = thicken(m, np.array([5, 5, 5]), voxel=1)
    assert new.shape == (3, 3, 3) and tuple(lo) == (4, 4, 4)
    assert new[1, 1, :].all() and new[:, 1, 1].all() and new.sum() == 7


def test_thicken_reaches_min_wall():
    """Eine 0.2 mm dünne Scheibe (Modellmass) wird mit «verdicken» ≥ 0.8 mm dick gedruckt."""
    pane = _box((20, 20, 0.2))
    pitch, min_wall = 0.4, 0.8
    without_it = voxelize([BuildingElement(pane)], pitch, scale=200)
    with_it = voxelize([BuildingElement(pane, thickening_voxel(0.2, min_wall, pitch))], pitch, scale=200)
    layers = lambda g: int(g.matrix.any(axis=(0, 1)).sum())
    assert layers(without_it) * pitch < min_wall
    assert layers(with_it) * pitch >= min_wall


# --- Gitteroperationen --------------------------------------------------------

def test_place_fills_and_clears_only_inside_body():
    """Voxel [i, j, k] hat das Zentrum (i, j, k); der Quader x 2.5..5.5 trifft genau x = 3, 4, 5."""
    voxel_grid = VoxelGrid(np.zeros((10, 10, 10), dtype=bool), np.zeros(3), 1.0)
    body = _box((3, 4, 2), (4, 4.5, 5))
    assert voxel_grid.place(body, True) == 3 * 4 * 2
    assert np.array_equal(np.unique(np.nonzero(voxel_grid.matrix)[0]), [3, 4, 5])
    assert voxel_grid.place(body, True) == 0                       # schon voll
    assert voxel_grid.place(body, False) == 24 and not voxel_grid.matrix.any()


def test_place_outside_the_grid():
    voxel_grid = VoxelGrid(np.zeros((4, 4, 4), dtype=bool), np.array([10.0, 10.0, 10.0]), 1.0)
    assert voxel_grid.place(_box((2, 2, 2)), True) == 0               # ganz daneben
    partially = _box((3.9, 3.9, 3.9), (10, 10, 10))                 # ragt über die Ecke hinaus
    assert voxel_grid.place(partially, True) == 2 * 2 * 2


def test_close_gaps_fills_1_voxel_slit():
    m = np.zeros((12, 12, 12), dtype=bool)
    m[2:5, 2:10, 2:10] = True
    m[6:9, 2:10, 2:10] = True                                       # Spalt bei x = 5
    assert close_gaps(m)[5, 3:9, 3:9].all()


def test_close_gaps_keeps_2_voxel_slit_and_stairs():
    m = np.zeros((20, 14, 14), dtype=bool)
    m[2:5, 2:12, 2:12] = True
    m[7:10, 2:12, 2:12] = True                                      # Spalt x = 5, 6 (2 Voxel)
    for i in range(3):                                              # Treppe: Auftritt 3, Steigung 2
        m[11 + 3 * i:20, 2:12, 0:2 * (i + 1)] = True
    assert np.array_equal(close_gaps(m), m)


def test_flatten_fills_slope_to_flat_plate():
    m = np.zeros((10, 4, 10), dtype=bool)
    for i in range(10):
        m[i, :, i // 3:i // 3 + 2] = True               # geneigte Platte, 2 Schichten dick
    flat = flatten(m)
    assert flat[:, :, 0:5].all() and not flat[:, :, 5:].any()
    assert (flat | m).sum() == flat.sum()               # nur ergänzt, nichts entfernt


def test_voxelize_collects_floor_plans_owners_and_roof():
    wall = BuildingElement(_box((1, 10, 5), (0.5, 5, 2.5)), storey="EG", guid="wand")
    slab = BuildingElement(_box((10, 10, 1), (5, 5, 5.5)), storey="EG", horizontal=True, guid="decke")
    roof = BuildingElement(_box((10, 10, 1), (5, 5, 8.5)), roof="Dach EG", guid="dach")
    voxel_grid = voxelize([wall, slab, roof], 1.0, 200)
    assert set(voxel_grid.floor_plans) == {"EG"}              # das Dachbauteil gehört zu keinem Grundriss
    assert voxel_grid.floor_plans["EG"].sum() == 100          # Wand und Decke, Lücken geschlossen
    assert voxel_grid.owners == [Owner("wand", "EG", None, False), Owner("decke", "EG", None, True),
                                 Owner("dach", "", "Dach EG", False)]
    assert voxel_grid.owner.shape == voxel_grid.matrix.shape
    assert (voxel_grid.owner == 2).sum() == 100               # das Dach: 10 × 10 × 1
    assert (voxel_grid.owner == 1).sum() == 100
    assert (voxel_grid.owner[~voxel_grid.matrix] == -1).all() and (voxel_grid.owner[voxel_grid.matrix] >= 0).any()
    assert [o.roof for o in voxel_grid.owners if o.roof] == ["Dach EG"]


def test_voxelize_slab_wins_where_a_wall_runs_through_it():
    wall = BuildingElement(_box((1, 1, 10), (5.5, 5.5, 5)), storey="EG", guid="wand")
    slab = BuildingElement(_box((10, 10, 1), (5.5, 5.5, 5.5)), storey="EG", horizontal=True, guid="decke")
    voxel_grid = voxelize([slab, wall], 1.0, 200)             # Reihenfolge der Eingabe egal: waagrechte Platten zuletzt
    owners = {o.guid: i for i, o in enumerate(voxel_grid.owners)}
    assert (voxel_grid.owner == owners["decke"]).sum() == 100  # die Decke ist vollständig
    assert (voxel_grid.owner == owners["wand"]).sum() == 9    # der Wand fehlt der Voxel, in dem die Decke liegt


def test_count_inside_body():
    voxel_grid = VoxelGrid(np.ones((6, 6, 6), dtype=bool), np.zeros(3), 1.0)
    assert voxel_grid.count_inside(_box((2, 2, 2), (2.5, 2.5, 2.5))) == 8


def test_specks_are_removed():
    from core.voxels.meshing import without_specks
    large = _box((10, 10, 10))
    speck = _box((0.2, 0.2, 0.2), (20, 0, 0))
    clean = without_specks(trimesh.util.concatenate([large, speck]))
    assert clean.volume == pytest.approx(1000)


# --- Gesamtgitter und Vernetzung ----------------------------------------------

def test_voxelize_reports_progress():
    cube = [BuildingElement(_box((10, 10, 10), (i * 20, 0, 0))) for i in range(3)]
    calls = []
    voxelize(cube, 1.0, 200, progress=lambda i, n: calls.append((i, n)))
    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_voxelize_without_elements():
    with pytest.raises(ValueError):
        voxelize([], 0.4, 200)


def test_meshing_watertight_and_dimensionally_accurate():
    cube = _box((10, 10, 10), (50, 50, 5))
    mesh = voxelize([BuildingElement(cube)], 0.5, 200).grid_to_mesh(postprocess=False)
    assert mesh.is_watertight and mesh.volume > 0
    assert mesh.volume == pytest.approx(1000, rel=0.05)
    assert np.allclose(mesh.bounds, cube.bounds, atol=0.5)


def test_enclosed_room_does_not_count_as_volume():
    """Regression: Innenschalen dürfen nicht nach aussen gedreht werden (alter fix_normals-Fehler)."""
    voxel_grid = VoxelGrid(_shell(20), np.zeros(3), 1.0)
    mesh = voxel_grid.grid_to_mesh()
    assert mesh.is_watertight
    assert mesh.volume == pytest.approx(voxel_grid.matrix.sum(), rel=0.1)


def test_to_mesh_layer_range():
    voxel_grid = VoxelGrid(np.ones((4, 4, 10), dtype=bool), np.zeros(3), 1.0)
    bottom, top = voxel_grid.grid_to_mesh(0, 5, postprocess=False), voxel_grid.grid_to_mesh(5, 10, postprocess=False)
    assert bottom.is_watertight and top.is_watertight
    assert bottom.bounds[1][2] == pytest.approx(top.bounds[0][2], abs=0.5)


# --- Robustheit (Analysebericht B-07, B-19) -----------------------------------------

def test_defective_element_is_skipped():
    """Ein Netz mit NaN bricht nicht mehr die ganze Erzeugung ab, sondern wird mit GUID gemeldet."""
    from core.voxels.grid import BuildingElement
    from core.voxels.shell import voxelize
    good = trimesh.creation.box(extents=(4, 4, 4))
    broken = trimesh.creation.box(extents=(4, 4, 4))
    broken.vertices[0] = np.nan
    voxel_grid = voxelize([BuildingElement(good, guid="gut"), BuildingElement(broken, guid="kaputt")], 0.4, 200)
    assert voxel_grid.matrix.sum() > 0
    assert len(voxel_grid.warnings) == 1 and "kaputt" in voxel_grid.warnings[0]
    with pytest.raises(ValueError, match="voxelisieren"):
        voxelize([BuildingElement(broken, guid="kaputt")], 0.4, 200)


def test_too_large_grid_clear_message(monkeypatch):
    """Ein Bauteil 800 m daneben oder ein Riesenmodell: Abbruch mit Hinweis statt Speicherüberlauf."""
    from core.voxels import shell
    from core.voxels.grid import BuildingElement
    from core.voxels.shell import voxelize
    monkeypatch.setattr(shell, "GRID_MAX_VOXELS", 10_000)
    monkeypatch.setattr(shell, "ram_bytes", lambda: None)
    far = trimesh.creation.box(extents=(4, 4, 4)).apply_translation([400, 0, 0])
    with pytest.raises(ValueError, match="zu gross"):
        voxelize([BuildingElement(trimesh.creation.box(extents=(4, 4, 4))), BuildingElement(far)], 0.4, 200)
    assert shell.grid_limit() == 10_000


def test_ram_on_every_operating_system():
    """Die Speicherbremse kennt den Arbeitsspeicher auf jedem Betriebssystem, auch unter Windows."""
    from core.voxels import shell
    ram = shell.ram_bytes()
    assert ram is not None and ram > 100_000_000
    assert shell.grid_limit() <= shell.GRID_MAX_VOXELS


def test_void_is_cut_only_from_its_own_element():
    """Ein Treppenauge wird aus der Decke geschnitten, die Treppe darin bleibt ganz."""
    from core.voxels.grid import BuildingElement
    from core.voxels.shell import voxelize
    slab = trimesh.creation.box(extents=(40, 40, 4))
    stairwell = trimesh.creation.box(extents=(10, 10, 8))                      # Öffnung, etwas höher als die Decke
    stair = trimesh.creation.box(extents=(4, 4, 20))                     # läuft durch das Auge
    with_it = voxelize([BuildingElement(slab, voids=[stairwell]), BuildingElement(stair)], 0.4, 200)
    without_it = voxelize([BuildingElement(slab), BuildingElement(stair)], 0.4, 200)
    center = tuple(int(round((0 - u) / 0.4)) for u in with_it.origin)        # Voxel bei (0, 0, 0)
    margin = (center[0] + 10, center[1], center[2])                             # 4 mm neben der Mitte: im Auge, neben der Treppe
    assert with_it.matrix[center] and not with_it.matrix[margin] and without_it.matrix[margin]
    assert with_it.matrix.sum() < without_it.matrix.sum()
