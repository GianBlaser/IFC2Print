"""Tests für core/parts/partitioning: Geschoss-Fugen, ganze Bauteile (Decken, Dächer, Deckel) und Druckbett-Packing."""

from pathlib import Path

import numpy as np
import pytest
import trimesh

from core.ifc.model import IfcModel
from core.parts import partitioning
from core.parts.cleanup import assign_by_support, assign_small_pieces, assign_with_message, without_sliver
from core.parts.print_layout import pack, print_plate
from core.parts.storey_joints import Joint, cuts, level_joints, storey_and_above, storey_heights
from core.voxels.grid import Owner, VoxelGrid

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


# --- Fuge eben halten (level_joints) -------------------------------------------------

def _labelled(m: np.ndarray, joint: int) -> np.ndarray:
    """Label-Gitter zu ``m``: unter der Fuge Teil 0, ab Schicht ``joint`` Teil 1, leer = −1."""
    labels = np.where(m, 0, -1).astype(np.int16)
    labels[:, :, joint:] = np.where(m[:, :, joint:], 1, -1)
    return labels


def _slab_with_ledge():
    """Raum (Wände x=0, x=19) mit Decke ab Schicht 10; unter x = 5..9 hängt 1 Schicht Dämmung."""
    m = np.zeros((20, 6, 20), dtype=bool)
    m[0] = m[-1] = True                                 # Wände
    m[:, :, 10:13] = True                               # Decke
    m[5:10, :, 9] = True                                # Dämmung 1 Schicht tiefer
    return m


def test_ledge_below_the_joint_is_trimmed():
    m = _slab_with_ledge()
    labels = _labelled(m, 10)
    labels[5:10, :, 9] = 1                              # die Dämmung gehört zum oberen Teil
    level_joints(m, labels, [Joint(1, 10, np.ones((20, 6), dtype=bool))], leveling=2)
    assert not m[5:10, :, 9].any() and (labels[5:10, :, 9] == -1).all()   # weg → Unterseite des oberen Teils eben
    assert m[0, :, 9].all() and (labels[0, :, 9] == 0).all()              # Wand des unteren Teils bleibt


def test_setback_above_the_joint_is_filled_up():
    m = np.zeros((20, 6, 20), dtype=bool)
    m[:, :, 10:13] = True
    m[5:10, :, 10] = False                              # Decke dort 1 Schicht dünner (Unterseite höher)
    labels = _labelled(m, 10)
    level_joints(m, labels, [Joint(1, 10, np.ones((20, 6), dtype=bool))], leveling=2)
    assert m[:, :, 10].all() and (labels[:, :, 10] == 1).all()


def test_deep_recess_and_lower_part_stay_untouched():
    """Was tiefer als ``leveling`` liegt, ist kein Absatz mehr: Es bleibt, ebenso alles vom unteren Teil."""
    m = np.zeros((20, 6, 20), dtype=bool)
    m[:, :, 10:13] = True
    m[5:10, :, 10:13] = False                           # Decke dort erst ab Schicht 13: 3 Voxel Rücksprung
    m[:, :, 5:8] = True                                 # Boden des unteren Teils
    labels = _labelled(m, 10)
    before_m, before_labels = m.copy(), labels.copy()
    level_joints(m, labels, [Joint(1, 10, np.ones((20, 6), dtype=bool))], leveling=2)
    assert (m == before_m).all() and (labels == before_labels).all()


def test_joint_only_levels_inside_its_columns():
    m = _slab_with_ledge()
    labels = _labelled(m, 10)
    labels[5:10, :, 9] = 1
    columns = np.zeros((20, 6), dtype=bool)
    columns[10:] = True                                 # Fuge gilt nur rechts; die Dämmung liegt links
    level_joints(m, labels, [Joint(1, 10, columns)], leveling=2)
    assert m[5:10, :, 9].all() and (labels[5:10, :, 9] == 1).all()


def test_joint_applies_where_this_or_higher_storey_stands():
    voxel_grid = VoxelGrid(np.zeros((4, 1, 4), dtype=bool), np.zeros(3), 1.0)
    g = {n: np.zeros((4, 1), dtype=bool) for n in ("EG", "OG", "DG")}
    g["EG"][0], g["OG"][1], g["DG"][2] = True, True, True
    above_mask = storey_and_above(voxel_grid, [("EG", 0), ("OG", 3), ("DG", 6)], g)
    assert above_mask["DG"][:, 0].tolist() == [False, False, True, False]
    assert above_mask["OG"][:, 0].tolist() == [False, True, True, False]
    assert above_mask["EG"][:, 0].tolist() == [True, True, True, False]


# --- Ganze Bauteile: Decken, Dächer, Deckel (partition_grid) --------------------------------------
# Massstab 200, Pitch 0.4 → 12.5 Voxel je realem Meter: LID_MIN_CLEARANCE_M = 12 Voxel Luft, ein Deckel braucht
# mindestens 1875 Spalten, ROOF_ZONE_MIN_HEIGHT_MM = 12.5 Voxel. Geschosse: EG bei Welt-Z 0, OG bei 8.0 (Schicht 20).

_STOREYS = [("EG", 0.0), ("OG", 8.0)]


def _box(x: tuple[int, int], y: tuple[int, int], z: tuple[int, int]) -> tuple[slice, slice, slice]:
    """Quader als Schnitt [von, bis) je Achse."""
    return slice(*x), slice(*y), slice(*z)


class _Scene:
    """Voxelgitter von Hand: ``add`` setzt ein Bauteil (wie core/voxels/shell._combine: wer später kommt,
    überschreibt – waagrechte Platten und Dächer gehören ans Ende)."""

    def __init__(self, shape: tuple[int, int, int]):
        self.matrix = np.zeros(shape, dtype=bool)
        self.owner = np.full(shape, -1, dtype=np.int16)
        self.owners: list[Owner] = []

    def add(self, region, *, storey="EG", roof=None, horizontal=False) -> np.ndarray:
        """``region``: Quader (``_box``) oder Bool-Gitter. Rückgabe: Maske der Voxel des Bauteils."""
        mask = region
        if isinstance(region, tuple):
            mask = np.zeros(self.matrix.shape, dtype=bool)
            mask[region] = True
        self.owners.append(Owner(f"g{len(self.owners)}", storey, roof, horizontal))
        self.matrix |= mask
        self.owner[mask] = len(self.owners) - 1
        return mask

    def grid(self, plans: dict[str, tuple[slice, slice]] | None = None) -> VoxelGrid:
        floor_plans = {}
        for name, (i, j) in (plans or {}).items():
            floor_plans[name] = np.zeros(self.matrix.shape[:2], dtype=bool)
            floor_plans[name][i, j] = True
        return VoxelGrid(self.matrix, np.zeros(3), 0.4, floor_plans=floor_plans, owner=self.owner, owners=self.owners)


def _partition(scene: _Scene, plans=None) -> partitioning.Partition:
    voxel_grid = scene.grid(plans)
    return partitioning.partition_grid(voxel_grid, _STOREYS, 200, floor_plans=voxel_grid.floor_plans or None)


def _above(mask: np.ndarray, k: int) -> np.ndarray:
    """``mask`` eingeschränkt auf die Schichten ab ``k``."""
    return mask & (np.arange(mask.shape[2]) >= k)[None, None, :]


def _box_house() -> _Scene:
    """EG und OG über 45 × 45 Spalten mit Bodenplatte (Schichten 0–1) und Aussenwänden (Schichten 2–39), die
    durch beide Geschosse laufen. Decken und Dach kommen in den Tests dazu."""
    s = _Scene((50, 50, 60))
    for x, y in (((0, 45), (0, 1)), ((0, 45), (44, 45)), ((0, 1), (1, 44)), ((44, 45), (1, 44))):
        s.add(_box(x, y, (2, 40)))
    s.add(_box((0, 45), (0, 45), (0, 2)), horizontal=True)
    return s


def test_slab_at_the_joint_goes_entirely_to_the_upper_part_even_if_its_underside_dips():
    s = _box_house()
    slab = np.zeros(s.matrix.shape, dtype=bool)
    slab[0:45, 0:45, 20:23] = True                                                     # Decke an der Fuge (Schicht 20)
    slab[10:20, 10:20, 19] = True                                                      # Unterseite stellenweise 1 tiefer
    s.add(slab, storey="OG", horizontal=True)
    t = _partition(s)
    assert t.names == ["EG", "OG"]
    assert (t.labels[slab & (np.arange(60) >= 20)[None, None, :]] == 1).all()          # ganz oben, nichts am EG
    assert (t.labels[10:20, 10:20, 19] == -1).all() and not s.matrix[10:20, 10:20, 19].any()   # Absatz abgeschnitten
    assert (t.labels[0:45, 0:45, 0:2] == 0).all()                                      # Bodenplatte bleibt unten
    assert (t.labels[1:44, 1:44, 2:19] == -1).all()                                    # Raum bleibt leer


def test_wall_head_below_a_thinner_slab_stays_with_the_lower_storey():
    s = _box_house()
    s.add(_box((30, 31), (5, 40), (2, 40)))                                            # Innenwand durch die Fuge
    slab = np.zeros(s.matrix.shape, dtype=bool)
    slab[0:45, 0:45, 20:24] = True
    slab[30, 5:40, 20:22] = False                                                      # an der Wand beginnt die Decke erst bei 22
    s.add(slab, storey="OG", horizontal=True)
    t = _partition(s)
    assert (t.labels[30, 5:40, 20:22] == 0).all()                                      # Wandkopf: unten (Schnitt je Spalte)
    assert (t.labels[30, 5:40, 22:24] == 1).all()                                      # die Decke darüber: oben
    assert (t.labels[30, 5:40, 24:40] == 1).all()                                      # Wand über der Decke: oben
    assert (t.labels[30, 5:40, 2:20] == 0).all()                                       # Wand unter der Fuge: unten
    assert (t.labels[10, 5:40, 20:24] == 1).all()                                      # Decke daneben: ganz oben


def test_sloped_slab_crossing_the_joint_stays_whole():
    s = _Scene((60, 50, 60))
    s.add(_box((0, 1), (0, 45), (2, 20)))                                              # eine Wand darunter
    s.add(_box((0, 26), (0, 45), (20, 23)), storey="OG", horizontal=True)              # ebene Decke: bestimmt die Fuge
    sloped = np.zeros(s.matrix.shape, dtype=bool)
    for i in range(26, 50):                                                            # steigt von Schicht 19 auf 23
        bottom = 19 + (i - 26) // 5
        sloped[i, 0:45, bottom:bottom + 3] = True
    s.add(sloped, storey="OG", horizontal=True)
    t = _partition(s)
    assert t.names == ["EG", "OG"]
    assert not (t.labels[sloped] == 0).any()                                           # nirgends am unteren Teil
    assert (t.labels[_above(sloped, 20)] == 1).all()
    assert (t.labels[26:30, 0:45, 19] == -1).all()                                     # nur der Absatz unter der Fuge entfällt


def _l_house() -> _Scene:
    """EG über x 0–69, OG nur über x 0–24. Rechts (x 25–69) liegt noch nichts über den Wänden des EG: Die Tests
    legen dort eine Terrasse auf die Schichten 15–16 (5 Schichten tiefer als die Decke unter dem OG, 20–22)."""
    s = _Scene((70, 56, 60))
    s.add(_box((0, 70), (0, 1), (2, 15)))                                              # Wände EG ringsum
    s.add(_box((0, 70), (55, 56), (2, 15)))
    s.add(_box((69, 70), (1, 55), (2, 15)))
    s.add(_box((24, 25), (1, 55), (2, 20)))
    s.add(_box((0, 70), (0, 56), (0, 2)), horizontal=True)                             # Bodenplatte
    s.add(_box((0, 25), (0, 56), (20, 23)), storey="OG", horizontal=True)              # Decke unter dem OG
    return s


_L_PLANS = {"EG": (slice(0, 70), slice(0, 56)), "OG": (slice(0, 25), slice(0, 56))}


def test_lower_slab_over_rooms_becomes_a_lid_part():
    s = _l_house()
    lid = s.add(_box((25, 70), (0, 56), (15, 17)), horizontal=True)                    # Terrasse über den Räumen
    t = _partition(s, _L_PLANS)
    assert t.names == ["EG", "OG", "Decke EG"]
    assert (t.labels[lid] == 2).all()
    assert (t.labels[69, 1:55, 2:15] == 0).all()                                       # Wand darunter bleibt beim EG
    assert (t.labels[0:25, 0:56, 20:23] == 1).all()                                    # Decke unter dem OG: OG
    parts = partitioning.mesh_pieces(s.grid(_L_PLANS), t)
    assert set(parts) == {"EG", "OG", "Decke EG"} and parts["Decke EG"].is_watertight


def test_flat_roof_slab_over_rooms_of_the_top_storey_is_named_roof():
    s = _box_house()
    s.add(_box((0, 45), (0, 45), (20, 23)), storey="OG", horizontal=True)
    roof = s.add(_box((0, 45), (0, 45), (38, 40)), storey="OG", horizontal=True)       # Flachdach ohne Dachbauteil
    t = _partition(s)
    assert t.names == ["EG", "OG", "Dach OG"]
    assert (t.labels[roof] == 2).all()
    assert (t.labels[0:45, 0:45, 20:23] == 1).all()                                    # die Decke an der Fuge ist KEIN Dach


def test_slab_at_the_joint_is_no_lid():
    """Auch gross und über Wänden des unteren Teils: Die Decke an der Fuge ist der Boden des oberen Teils."""
    s = _box_house()
    s.add(_box((0, 45), (0, 45), (20, 23)), storey="OG", horizontal=True)
    t = _partition(s)
    assert t.names == ["EG", "OG"] and (t.labels[0:45, 0:45, 20:23] == 1).all()


def test_covering_on_a_lid_goes_with_the_lid():
    s = _l_house()
    s.add(_box((25, 70), (0, 56), (15, 17)), horizontal=True)                          # Terrasse
    covering = s.add(_box((30, 60), (10, 40), (17, 18)), horizontal=True)              # Belag, liegt direkt auf
    t = _partition(s, _L_PLANS)
    assert t.names == ["EG", "OG", "Decke EG"]
    assert (t.labels[covering] == 2).all()


def test_covering_with_a_small_air_gap_goes_with_the_lid():
    s = _l_house()
    s.add(_box((25, 70), (0, 56), (15, 17)), horizontal=True)
    covering = s.add(_box((30, 60), (10, 40), (19, 20)), horizontal=True)             # 2 Schichten Luft darunter
    t = _partition(s, _L_PLANS)
    assert t.names == ["EG", "OG", "Decke EG"]
    assert (t.labels[covering] == 2).all()


def test_insulation_just_below_the_slab_of_the_storey_above_goes_with_that_storey():
    s = _box_house()
    insulation = s.add(_box((2, 43), (2, 43), (17, 19)), horizontal=True)             # 1 Schicht Luft unter der Decke
    s.add(_box((0, 45), (0, 45), (20, 23)), storey="OG", horizontal=True)
    t = _partition(s)
    assert t.names == ["EG", "OG"]
    assert (t.labels[insulation] == 1).all()                                           # oberes Teil, nicht EG


def _roof_scene(roof_height: int) -> tuple[_Scene, np.ndarray]:
    s = _box_house()
    s.add(_box((0, 45), (0, 45), (20, 23)), storey="OG", horizontal=True)
    roof = s.add(_box((10, 30), (10, 30), (40, 40 + roof_height)), storey="OG", roof="Dach OG")
    return s, roof


def test_small_roof_becomes_its_own_part_and_is_not_cut():
    s, roof = _roof_scene(roof_height=14)                                              # 5600 Voxel: weit unter 1 % des Modells
    t = _partition(s)
    assert t.names == ["EG", "OG", "Dach OG"]
    assert (t.labels[roof] == 2).all()
    parts = partitioning.mesh_pieces(s.grid(), t)
    assert list(parts) == ["EG", "OG", "Dach OG"] and all(x.is_watertight for x in parts.values())


def test_roof_is_one_part_per_connected_piece():
    s, roof = _roof_scene(roof_height=14)
    second = s.add(_box((10, 30), (33, 43), (40, 54)), storey="OG", roof="Dach OG")   # 2800 Voxel, getrennt vom ersten
    t = _partition(s)
    assert t.names == ["EG", "OG", "Dach OG", "Dach OG"]
    assert (t.labels[roof] == 2).all() and (t.labels[second] == 3).all()
    assert list(partitioning.mesh_pieces(s.grid(), t)) == ["EG", "OG", "Dach OG", "Dach OG #2"]


def test_low_roof_is_treated_like_a_slab():
    s, roof = _roof_scene(roof_height=6)                                               # 6 Schichten = 0.5 m: keine Dachschale
    t = _partition(s)
    assert "Dach OG" not in t.names
    assert (t.labels[roof] == 1).all()                                                 # wie eine Decke: ans Geschoss


# --- Abgetrennte Stücke und Kleinteile (cleanup) ------------------------------------

def test_piece_on_the_roof_goes_to_the_roof():
    labels = np.full((20, 20, 30), -1, dtype=np.int16)
    labels[:, :, :10] = 0                               # Geschoss
    labels[:, :, 10:14] = 2                             # Dach darüber
    labels[5:7, 5:7, 14:17] = 0                         # Brüstung (Label 0) steht auf dem Dach, hängt nicht am Hauptstück
    assert assign_by_support(labels) == (1, 0)
    assert (labels[5:7, 5:7, 14:17] == 2).all() and (labels[:, :, :10] == 0).all()


def test_piece_without_support_goes_to_the_part_it_touches_sideways():
    labels = np.full((20, 20, 30), -1, dtype=np.int16)
    labels[0:10, :, 0:10] = 0
    labels[10:20, :, 0:20] = 1                          # Nachbarteil, höher
    labels[8:10, 5:7, 12:14] = 0                        # Stück von 0 schwebt neben 1: unten Luft, seitlich Teil 1
    assert assign_by_support(labels) == (1, 0)
    assert (labels[8:10, 5:7, 12:14] == 1).all()


def test_part_above_the_piece_is_no_support():
    labels = np.full((20, 20, 30), -1, dtype=np.int16)
    labels[0:5, :, 0:5] = 0                             # Hauptstück von 0, weit weg
    labels[10:20, :, 10:20] = 1                         # Teil 1 liegt auf dem Stück:
    labels[12:14, 5:7, 8:10] = 0                        # das Stück hängt darunter, Teil 1 trägt es nicht
    assert assign_by_support(labels) == (0, 2 * 2 * 2)
    assert (labels[12:14, 5:7, 8:10] == -1).all() and (labels[10:20, :, 10:20] == 1).all()


def test_sliver_without_contact_is_deleted():
    labels = np.full((20, 20, 20), -1, dtype=np.int16)
    labels[0:10] = 0
    labels[10:20] = 1
    labels[17:20, 17:20, 17:20] = -1
    labels[18, 18, 18] = 1                              # loser Splitter von 1 ohne jeden Kontakt
    assert assign_by_support(labels) == (0, 1)
    assert labels[18, 18, 18] == -1 and (labels[10:17] == 1).all()


def test_main_piece_stays_even_if_it_is_not_the_lowest():
    labels = np.full((20, 20, 30), -1, dtype=np.int16)
    labels[:, :, :10] = 0
    labels[:, :, 10:20] = 1                             # zusammenhängend: kein abgetrenntes Stück
    before = labels.copy()
    assert assign_by_support(labels) == (0, 0) and (labels == before).all()


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
    warnings = assign_with_message(labels, ["EG", "OG", "Technik"], 3, 0.4)
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


def test_roofs_and_lids_are_not_dissolved_as_small_parts():
    labels = np.full((20, 20, 20), -1, dtype=np.int16)
    labels[:, :, :10] = 0
    labels[:, :, 10:18] = 1
    labels[5, 5, 18] = 2                                # kleines Dach (Teil 2 ≥ Anzahl der Geschosse) auf dem OG
    assert assign_small_pieces(labels, count=2) == 0
    assert labels[5, 5, 18] == 2
    assert assign_small_pieces(labels) == 1             # ohne Anzahl gälte es als Kleinteil
    assert labels[5, 5, 18] == 1


def test_small_storey_part_is_still_dissolved_next_to_a_roof():
    labels = np.full((20, 20, 20), -1, dtype=np.int16)
    labels[:, :, :10] = 0
    labels[:, :, 10:18] = 2                             # Dach
    labels[5, 5, 18] = 1                                # Geschoss 1 besteht nur aus einem Voxel
    assert assign_small_pieces(labels, count=2) == 1
    assert labels[5, 5, 18] == 2


def test_small_roof_survives_assign_with_message():
    labels = np.full((20, 20, 20), -1, dtype=np.int16)
    labels[:, :, :10] = 0
    labels[:, :, 10:18] = 1
    labels[5, 5, 18:20] = 2
    warnings = assign_with_message(labels, ["EG", "OG", "Dach OG"], 2, 0.4)
    assert (labels[5, 5, 18:20] == 2).all() and not any("Dach OG" in w for w in warnings)


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
