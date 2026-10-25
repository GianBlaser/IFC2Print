"""Tests für core/parts/partitioning: Geschoss-Fugen und Druckbett-Packing."""

from pathlib import Path

import numpy as np
import pytest
import trimesh

from core.ifc.model import IfcModel
from core.parts import partitioning
from core.parts.cleanup import assign_islands, assign_small_pieces, assign_with_message, without_sliver
from core.parts.print_layout import pack, print_plate
from core.parts.storey_joints import (cuts, flat_undersides, flush_slabs, smooth_joint, storey_and_above,
                                      storey_heights)
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
    r, filled, kept = without_sliver(m, 8)
    assert not r[8, 8, 8] and r[4, 4, 4] and r[10:12, 0:2, 0:3].all()
    assert r.sum() == 6 ** 3 + 12
    assert filled == kept == []                  # der 1-Voxel-Hohlraum ist ein Vernetzungsrest, keine Meldung
    assert without_sliver(m, 1)[0] is m          # grobe Voxel: nichts zu tun


def test_closed_cavities_up_to_the_limit_are_filled():
    m = np.zeros((20, 20, 20), dtype=bool)
    m[1:19, 1:19, 1:19] = True
    m[3:6, 3:6, 3:6] = False                     # Schacht 27 Voxel
    m[8:16, 8:16, 8:16] = False                  # grosser Hohlraum 512 Voxel
    r, filled, kept = without_sliver(m, 8, max_cavity=100)
    assert r[3:6, 3:6, 3:6].all() and not r[8:16, 8:16, 8:16].any()
    assert filled == [27] and kept == [512]
    open_box = m.copy()
    open_box[3:6, 3:6, 0:3] = False              # nach unten offen: kein geschlossener Hohlraum
    r, filled, _ = without_sliver(open_box, 8, max_cavity=100)
    assert filled == [] and not r[3:6, 3:6, 3:6].any()


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


def _house(lower_ceiling: int = 20) -> tuple[VoxelGrid, dict[str, np.ndarray]]:
    """EG über die ganze Länge (x 0–29), OG nur links (x 0–14); Pitch 0.4, 1:200 (Geschoss 20 Schichten = 4 m).

    ``lower_ceiling``: Unterseite der EG-Decke rechts (x 16–29); 20 = bündig mit der Decke unter dem OG.
    """
    m = np.zeros((30, 20, 44), dtype=bool)
    m[:, :, 0:2] = True                                     # Bodenplatte EG
    m[[0, 15, 29], :, 2:20] = True                          # Wände EG (x = 15 trägt beide Decken)
    m[:, [0, 19], 2:20] = True
    m[0:16, :, 20:22] = True                                # Decke unter dem OG
    m[16:30, :, lower_ceiling:lower_ceiling + 2] = True     # Decke rechts
    m[[29], :, lower_ceiling:20] = True                     # Wand rechts bis unter die tiefere Decke
    m[[0, 14], :, 22:42] = m[0:15, [0, 19], 22:42] = True   # Wände OG
    m[0:15, :, 42:44] = True                                # Dach OG (flach)
    plans = {"EG": np.ones((30, 20), dtype=bool), "OG": np.zeros((30, 20), dtype=bool)}
    plans["OG"][0:15] = True
    return VoxelGrid(m, np.zeros(3), 0.4), plans


def test_flush_slab_beyond_the_upper_floor_plan_goes_up():
    voxel_grid, plans = _house()
    t = partitioning.partition_grid(voxel_grid, [("EG", 0.0), ("OG", 8.0)], 200, floor_plans=plans)
    assert t.names == ["EG", "OG"]
    assert (t.labels[16:30, :, 20:22] == 1).all()          # Decke rechts gehört zum OG: das EG bleibt oben offen
    assert (t.labels[29, :, 2:20] == 0).all()              # die Wand darunter bleibt beim EG


def test_flush_slabs_ignore_walls_running_through_the_joint():
    m = np.zeros((20, 10, 30), dtype=bool)
    m[0:12, :, 10:12] = True                               # Decke, bündig an der Fuge 10
    m[12, :, :] = True                                     # hohe Wand eines Flügels durch die Fuge
    columns = np.zeros((20, 10), dtype=bool)
    columns[0:5] = True
    grown = flush_slabs(m, 10, columns, leveling=1, plate=12)
    assert grown[0:12].all() and not grown[12:].any()


def test_deep_ceiling_over_rooms_becomes_own_part():
    voxel_grid, plans = _house(lower_ceiling=15)           # rechts 5 Schichten (1 m) tiefer: Deckel über dem EG
    t = partitioning.partition_grid(voxel_grid, [("EG", 0.0), ("OG", 8.0)], 200, floor_plans=plans)
    assert t.names == ["EG", "OG", "Decke EG"]
    assert (t.labels[16:29, 1:19, 15:17] == 2).all()       # die tiefere Decke ist ein eigenes Teil
    assert (t.labels[29, 1:19, 2:15] == 0).all()           # die Wand darunter bleibt beim EG
    parts = partitioning.mesh_pieces(voxel_grid, t)
    assert set(parts) == {"EG", "OG", "Decke EG"} and parts["Decke EG"].is_watertight


def _slab_over_storey(thickness: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Labels und Gitter: unten Teil 0 (Schichten 0–4), darüber die Decke von Teil 1 ab der Fuge 5."""
    labels = np.full((20, 20, 12), -1, dtype=np.int16)
    labels[:, :, :5] = 0
    labels[:, :, 5:5 + thickness] = 1
    return labels, labels >= 0


def _flatten(labels: np.ndarray, m: np.ndarray) -> dict:
    return flat_undersides(labels, m, [(1, 5, np.ones((20, 20), dtype=bool))], depth=4, radius=2)


def test_narrow_recess_in_the_underside_is_filled():
    labels, m = _slab_over_storey()
    labels[5:15, 8:10, 5:7] = -1                            # Storenkasten-Rinne: 2 Voxel breit, 2 tief
    m[5:15, 8:10, 5:7] = False
    assert _flatten(labels, m) == {1: (1, 40)}
    assert (labels[:, :, 5:9] == 1).all() and m[:, :, 5:9].all()


def test_wide_or_deep_recesses_stay_open():
    labels, m = _slab_over_storey(thickness=6)
    labels[2:10, 2:10, 5:7] = -1                            # breit (Treppenauge, Deckenversatz)
    labels[12:18, 15:17, 5:10] = -1                         # schmal, aber tiefer als depth
    before = labels.copy()
    assert _flatten(labels, labels >= 0) == {}
    assert (labels == before).all()


def test_roof_voxels_in_a_recess_stay_with_the_roof():
    labels, m = _slab_over_storey()
    labels[5:15, 8:10, 5] = 2                               # Dachvoxel in der Rinne
    labels[5:15, 8:10, 6] = -1
    before = labels.copy()
    assert _flatten(labels, labels >= 0) == {}
    assert (labels == before).all()


def test_partition_flattens_the_underside_and_reports_it():
    m = np.zeros((30, 30, 30), dtype=bool)
    m[0], m[-1], m[:, 0], m[:, -1] = (True,) * 4             # Aussenwände über beide Geschosse
    m[:, :, :2] = m[:, :, 12:16] = True                     # Bodenplatte, Decke ab Fuge 12
    m[10:20, 14:16, 12:14] = False                          # Rinne 2 Voxel breit, 2 tief (tiefer als JOINT_LEVELING_MM)
    t = partitioning.partition_grid(VoxelGrid(m, np.zeros(3), 0.4), [("EG", 0.0), ("OG", 4.8)], 200)
    assert (t.labels[1:-1, 1:-1, 12] == 1).all()
    assert any("Unterseite eben" in w for w in t.warnings)
