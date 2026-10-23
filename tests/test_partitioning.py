"""Tests für core/parts/partitioning: Geschoss-Fugen und Druckbett-Packing."""

from pathlib import Path

import numpy as np
import pytest
import trimesh

from core.ifc.model import IfcModel
from core.parts import partitioning
from core.parts.cleanup import assign_islands, assign_small_pieces, assign_with_message, without_sliver
from core.parts.print_layout import pack, print_plate
from core.parts.storey_joints import cuts, smooth_joint, storey_and_above, storey_heights
from core.voxels.grid import VoxelGrid

_MFH = Path(__file__).parent.parent / "testdaten" / "MFH_eBKPH_Real.ifc"


def _two_storeys() -> VoxelGrid:
    """Kasten mit Umfassungswänden und drei Decken (unten / mitte / oben), Pitch 0.4."""
    m = np.zeros((12, 12, 20), dtype=bool)
    m[0], m[-1], m[:, 0], m[:, -1] = (True,) * 4
    m[:, :, 0] = m[:, :, 10] = m[:, :, 19] = True
    return VoxelGrid(m, np.zeros(3), 0.4)


def test_cut_finds_middle_slab():
    ranges, warnings = cuts(_two_storeys(), [("EG", 0.0), ("OG", 4.0)], scale=200)
    assert ranges == [("EG", 0, 10), ("OG", 10, 20)]
    assert not warnings


def test_pieces_watertight_and_joint_planar():
    voxel_grid = _two_storeys()
    ranges, _ = cuts(voxel_grid, [("EG", 0.0), ("OG", 4.0)], 200)
    parts = {name: voxel_grid.grid_to_mesh(start_idx, stop_idx) for name, start_idx, stop_idx in ranges}
    assert set(parts) == {"EG", "OG"}
    assert all(t.is_watertight for t in parts.values())
    assert abs(parts["EG"].bounds[1][2] - parts["OG"].bounds[0][2]) < 0.4


def test_warning_without_clear_slab():
    voxel_grid = VoxelGrid(np.ones((8, 8, 20), dtype=bool), np.zeros(3), 0.4)
    ranges, warnings = cuts(voxel_grid, [("EG", 0.0), ("OG", 4.0)], 200)
    assert warnings and ranges[0][2] == 10


def test_one_storey_one_part():
    voxel_grid = _two_storeys()
    assert cuts(voxel_grid, [("EG", 0.0)], 200) == ([("EG", 0, 20)], [])
    assert cuts(voxel_grid, [], 200) == ([("Modell", 0, 20)], [])


def test_storey_heights_from_placement():
    ifc = IfcModel.open_file(_MFH)
    heights = storey_heights(ifc.model, 200)
    assert [n for n, _ in heights] == ["UG", "EG", "1. OG", "2. OG", "Attika", "Dach"]
    assert [z for _, z in heights] == sorted(z for _, z in heights)


# --- Druckbett ------------------------------------------------------------------

def test_pack_everything_on_one_print_bed():
    layout = pack([(f"G{i}", 100.0, 60.0) for i in range(4)], 250, 210, 8)
    assert {print_bed for _, print_bed, *_ in layout} == {0}
    assert all(x + 100 <= 250 and y + 60 <= 210 for _, _, x, y, _ in layout)


def test_pack_several_print_beds():
    layout = pack([(f"T{i}", 120.0, 90.0) for i in range(10)], 250, 210, 8)
    assert max(print_bed for _, print_bed, *_ in layout) + 1 == 3


def test_pack_rotates_to_fit():
    (_, print_bed, _, _, rotated), = pack([("hoch", 80.0, 230.0)], 250, 210, 8)
    assert rotated and print_bed == 0


def test_print_plate_lies_at_z0():
    parts = {n: trimesh.creation.box(extents=(50, 40, 20)).apply_translation([0, 0, 100 * i])
             for i, n in enumerate("ABC")}
    plate = print_plate(parts, 250, 210)
    assert plate.bounds[0][2] == pytest.approx(0)
    assert plate.bounds[1][2] == pytest.approx(20)


# --- Fuge glätten, Teile, Inseln -------------------------------------------------

def _slab_with_ledge():
    """Raum (Wände x=0, x=19) mit Decke ab Schicht 10; unter x = 5..9 hängt 1 Schicht Dämmung."""
    m = np.zeros((20, 6, 20), dtype=bool)
    m[0] = m[-1] = True                                 # Wände
    m[:, :, 10:13] = True                               # Decke
    m[5:10, :, 9] = True                                # Dämmung 1 Schicht tiefer
    return m


def test_ledge_below_the_joint_is_trimmed():
    m = _slab_with_ledge()
    height = smooth_joint(m, 10, np.ones((20, 6), dtype=bool), leveling=2, plate=5, width=0)
    assert not m[5:10, :, 9].any()                      # Dämmung weg → Unterseite des oberen Teils eben
    assert (height == 10).all() and m[0, :, 9].all()     # Wände bleiben


def test_setback_above_the_joint_is_filled_up():
    m = np.zeros((20, 6, 20), dtype=bool)
    m[:, :, 10:13] = True
    m[5:10, :, 10] = False                              # Decke dort 1 Schicht dünner (Unterseite höher)
    smooth_joint(m, 10, np.ones((20, 6), dtype=bool), leveling=2, plate=5, width=0)
    assert m[:, :, 10].all()


def test_deep_wide_slab_goes_all_the_way_down_narrow_girder_is_cut():
    m = np.zeros((30, 30, 20), dtype=bool)
    m[:, :, 10:13] = True                               # Decke, Fuge bei 10
    m[:15, :, 6:10] = True                              # links: Decke reicht 4 Schichten tiefer (breit)
    m[20:22, :, 6:10] = True                            # rechts: Unterzug, 2 Voxel breit
    height = smooth_joint(m, 10, np.ones((30, 30), dtype=bool), leveling=2, plate=8, width=3)
    assert (height[3:12, 3:27] == 13).all()              # über der tiefen Decke → ganze Decke unten
    assert (height[20:22, :] == 10).all()                # Unterzug: Schnitt bei 10
    assert m[20:22, :, 6:10].all()                      # und bleibt erhalten


def test_without_floor_plan_no_joint():
    m = _slab_with_ledge()
    columns = np.zeros((20, 6), dtype=bool)
    columns[10:] = True
    height = smooth_joint(m, 10, columns, leveling=2, plate=5, width=0)
    assert (height[:10] == 20).all() and (height[10:] == 10).all()


def test_joint_applies_where_this_or_higher_storey_stands():
    voxel_grid = VoxelGrid(np.zeros((4, 1, 4), dtype=bool), np.zeros(3), 1.0)
    g = {n: np.zeros((4, 1), dtype=bool) for n in ("EG", "OG", "DG")}
    g["EG"][0], g["OG"][1], g["DG"][2] = True, True, True
    above_mask = storey_and_above(voxel_grid, [("EG", 0), ("OG", 3), ("DG", 6)], g)
    assert above_mask["DG"][:, 0].tolist() == [False, False, True, False]
    assert above_mask["OG"][:, 0].tolist() == [False, True, True, False]
    assert above_mask["EG"][:, 0].tolist() == [True, True, True, False]


def test_islands_switch_to_neighbor_slivers_are_dropped():
    labels = np.full((20, 20, 20), -1, dtype=np.int16)
    labels[0:10] = 0                                    # Teil 0
    labels[10:20] = 1                                   # Teil 1
    labels[12:14, 5:7, 5:7] = 0                         # Insel von 0 mitten in 1
    labels[17:20, 17:20, 17:20] = -1
    labels[18, 18, 18] = 1                              # loser Splitter von 1 (ohne Kontakt)
    assign_islands(labels)
    assert (labels[12:14, 5:7, 5:7] == 1).all()
    assert labels[18, 18, 18] == -1


def test_roof_becomes_own_part_and_is_not_cut():
    m = np.zeros((10, 10, 30), dtype=bool)
    m[:, :, 0:2] = m[:, :, 14:16] = True                # Böden EG, OG
    m[0, :, :] = m[-1, :, :] = True                     # Wände bis oben
    roof = np.full(m.shape, -1, dtype=np.int8)
    roof[:, :, 26:30] = 0
    m[:, :, 26:30] = True
    voxel_grid = VoxelGrid(m, np.zeros(3), 0.4)
    t = partitioning.partition_grid(voxel_grid, [("EG", 0.0), ("OG", 5.6)], 200, roof=roof, roof_names=["Dach OG"])
    assert t.names == ["EG", "OG", "Dach OG"]
    assert (t.labels[:, :, 26:30] == 2).all()
    parts = partitioning.mesh_pieces(voxel_grid, t)
    assert list(parts) == ["EG", "OG", "Dach OG"] and all(x.is_watertight for x in parts.values())


def test_tiny_part_goes_to_the_neighbor_part():
    labels = np.full((20, 20, 20), -1, dtype=np.int16)
    labels[:, :, :10] = 0
    labels[:, :, 10:19] = 1
    labels[5, 5, 19] = 2                                # Restteil aus einem Voxel auf Teil 1
    assert assign_small_pieces(labels) == 1
    assert labels[5, 5, 19] == 1 and set(np.unique(labels)) == {-1, 0, 1}


def test_dissolved_part_appears_as_warning():
    """Keine stillen Fehler: Ein Teil, das im Nachbarteil aufgeht, wird mit Namen gemeldet."""
    labels = np.full((20, 20, 20), -1, dtype=np.int16)
    labels[:, :, :10] = 0
    labels[:, :, 10:19] = 1
    labels[5, 5, 19] = 2
    warnings = assign_with_message(labels, ["EG", "OG", "Technik"], 3, 2, 0.4)
    assert any("«Technik»" in w and "angehängt" in w for w in warnings)


# --- Splitter im Gitter, eindeutige Teile (Analysebericht B-04, B-11, B-16) ----------

def test_without_slivers_removes_specks_and_fills_small_cavities():
    m = np.zeros((12, 12, 12), dtype=bool)
    m[2:8, 2:8, 2:8] = True
    m[4, 4, 4] = False                       # Hohlraum aus 1 Voxel
    m[8, 8, 8] = True                        # Krume, nur über eine Ecke verbunden
    m[10:12, 0:2, 0:3] = True                # loses Stück mit 12 Voxeln bleibt
    r = without_sliver(m, 8)
    assert not r[8, 8, 8] and r[4, 4, 4] and r[10:12, 0:2, 0:3].all()
    assert r.sum() == 6 ** 3 + 12
    assert without_sliver(m, 1) is m             # grobe Voxel: nichts zu tun


def test_mesh_pieces_without_specks_and_unique():
    m = np.zeros((10, 10, 12), dtype=bool)
    m[1:9, 1:9, 1:5] = m[1:9, 1:9, 6:10] = True
    m[0, 0, 11] = True                                       # Einzelvoxel (0.064 mm³ < 0.5 mm³)
    labels = np.where(m, 0, -1).astype(np.int16)
    labels[:, :, 6:] = np.where(m[:, :, 6:], 1, -1)
    labels[0, 0, 11] = 1
    partition = partitioning.Partition(labels, ["EG", "EG"], [])
    parts = partitioning.mesh_pieces(VoxelGrid(m, np.zeros(3), 0.4), partition)
    assert list(parts) == ["EG", "EG #2"]
    assert all(t.is_watertight and t.body_count == 1 for t in parts.values())
    assert parts["EG #2"].volume == pytest.approx(8 * 8 * 4 * 0.4 ** 3, rel=0.05)


def test_hanging_steps_go_to_the_neighbor_part():
    """Ein Block unter der Unterseite des oberen Teils (Treppenende in der Deckenöffnung) hebt es nicht vom Bett."""
    from core.parts.cleanup import assign_hanging
    labels = np.full((20, 20, 30), -1, dtype=np.int16)
    labels[:, :, :10] = 0
    labels[:, :, 10:20] = 1                 # oberes Teil, Unterseite bei k = 10
    labels[:, :, 6:10][5:8, 5:8] = 1        # Block ragt 4 Schichten unter die Unterseite, seitlich liegt Teil 0
    assert assign_hanging(labels, 2, 6) == 3 * 3 * 4
    assert (labels[5:8, 5:8, 6:10] == 0).all() and (labels[:, :, 10:20] == 1).all()


def test_hanging_steps_without_neighbor_are_trimmed():
    from core.parts.cleanup import assign_hanging
    labels = np.full((20, 20, 30), -1, dtype=np.int16)
    labels[:, :, 10:20] = 1
    labels[:, :, 6:10][5:8, 5:8] = 1        # schwebt unter dem Teil, ringsum Luft
    assert assign_hanging(labels, 2, 6) == 3 * 3 * 4
    assert (labels[:, :, :10] == -1).all()


def test_slab_underside_below_wall_of_upper_storey_is_trimmed():
    """NEST 1:100: Wand oben steht auf einer Decke, deren Unterseite 1 Schicht unter der Fuge liegt.
    Ohne Wand darunter blieb diese Schicht als dünner Streifen oben auf dem unteren Teil."""
    m = np.zeros((20, 6, 30), dtype=bool)
    m[:, :, 10:12] = True                               # Decke des oberen Geschosses
    m[:, :, 9] = True                                   # Unterseite 1 Schicht unter der Fuge (k = 10)
    m[8:10, :, 12:30] = True                            # Wand des oberen Geschosses → Vollabschnitt > platte
    m[0, :, :9] = True                                  # Wand des unteren Geschosses (am Rand)
    smooth_joint(m, 10, np.ones((20, 6), dtype=bool), leveling=2, plate=5, width=0)
    assert not m[8:10, :, 9].any()                      # unter der oberen Wand: kein Streifen mehr
    assert m[0, :, 8].all()                             # untere Wand bleibt
