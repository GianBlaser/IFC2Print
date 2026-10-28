"""Steckverbinder: Planung auf den Kontaktflächen, Zapfen/Taschen als Kegelstümpfe."""

import numpy as np
import pytest

from config import MIN_ENGAGEMENT_MM, CLEARANCE_MM, PEG_DEPTH_RATIO
from core.connectors import geometry
from core.connectors.geometry import apply_connectors, Connector
from core.connectors.planning import plan_connectors
from core.parts.partitioning import Partition
from core.parts.storey_joints import Joint, level_joints
from core.voxels.grid import VoxelGrid
from core.voxels.meshing import marching_cubes

PITCH = 0.4
CLEARANCE = CLEARANCE_MM          # Passungsspiel wie im Betrieb (0.20 mm)


def _house(inside: int = 100, wall: int = 5, floor_thickness: int = 3, height: int = 30, slab: int = 5, pillar: int = 0):
    """Zwei Teile übereinander: unten Boden + Wände (Raum offen), oben Decke + Wände (Label 0 / 1)."""
    n = inside + 2 * wall
    labels = np.full((n, n, floor_thickness + height + slab + 20), -1, dtype=np.int16)
    ring = np.ones((n, n), dtype=bool)
    ring[wall:-wall, wall:-wall] = False
    if pillar:
        m = n // 2
        ring[m - pillar // 2:m + pillar - pillar // 2, m - pillar // 2:m + pillar - pillar // 2] = True
    labels[:, :, :floor_thickness] = 0                                   # Bodenplatte unten
    labels[ring, floor_thickness:floor_thickness + height] = 0                      # Wände (und Stütze) unten
    k0 = floor_thickness + height
    labels[:, :, k0:k0 + slab] = 1                            # Decke des oberen Teils
    labels[ring, k0 + slab:] = 1                              # Wände oben
    voxel_grid = VoxelGrid(labels >= 0, np.zeros(3), PITCH)
    partition = Partition(labels, ["unten", "oben"], [])
    return voxel_grid, partition


def _parts(voxel_grid, partition):
    return {n: marching_cubes(partition.labels == number, voxel_grid.origin, PITCH) for number, n in enumerate(partition.names)}


def test_three_rectangular_pegs_on_the_walls():
    voxel_grid, partition = _house()
    plan, warnings = plan_connectors(voxel_grid, partition, CLEARANCE)
    assert not warnings
    assert len(plan) == 3
    for v in plan:
        assert v.width >= 1.2 and v.length >= 2.4
        assert v.height == pytest.approx(PEG_DEPTH_RATIO * 5 * PITCH)
    points = np.array([(v.x, v.y) for v in plan])
    sides = np.linalg.norm(points - np.roll(points, 1, axis=0), axis=1)
    assert sides.min() >= 10.0                               # weit verteilt
    # keine Säule: alle Zapfen stehen auf der Wandkrone (Ring), nicht im Raum
    for v in plan:
        i, j = int(round(v.x / PITCH)), int(round(v.y / PITCH))
        assert partition.labels[i, j, 3 + 30 - 1] == 0


def test_pillars_get_round_pegs():
    """Decke nur auf drei Stützen (8 × 8 Voxel): drei runde Zapfen, je einer pro Stütze."""
    labels = np.full((80, 80, 40), -1, dtype=np.int16)
    labels[:, :, :3] = 0
    pillars = [(10, 10), (60, 10), (35, 60)]
    for i, j in pillars:
        labels[i:i + 8, j:j + 8, 3:30] = 0
    labels[:, :, 30:35] = 1
    voxel_grid = VoxelGrid(labels >= 0, np.zeros(3), PITCH)
    plan, warnings = plan_connectors(voxel_grid, Partition(labels, ["unten", "oben"], []), CLEARANCE)
    assert not warnings and len(plan) == 3
    assert all(v.is_round and v.width >= 2.4 for v in plan)
    centers = {(round(v.x / PITCH), round(v.y / PITCH)) for v in plan}
    assert all(any(abs(i + 3.5 - x) <= 1 and abs(j + 3.5 - y) <= 1 for x, y in centers) for i, j in pillars)


def test_apply_watertight():
    voxel_grid, partition = _house()
    parts = _parts(voxel_grid, partition)
    plan, _ = plan_connectors(voxel_grid, partition, CLEARANCE)
    new, warnings = apply_connectors(parts, {0: "unten", 1: "oben"}, plan, CLEARANCE)
    assert not warnings
    for m in new.values():
        assert m.is_watertight
    assert new["unten"].volume > parts["unten"].volume          # Zapfen
    assert new["oben"].volume < parts["oben"].volume            # Taschen
    # Tasche bleibt Sackloch: Deckenoberseite unverändert geschlossen
    assert new["oben"].bounds[1][2] == pytest.approx(parts["oben"].bounds[1][2])


def test_levelled_underside_keeps_the_connectors():
    """Storenkasten-Rinne über der Wandkrone: nach ``level_joints`` dieselben Verbinder wie ohne Rinne.

    Die Rinne ist 2 Voxel tief, ``leveling`` 2: Sie gilt als Rücksprung der Deckenunterseite und wird aufgefüllt.
    """
    clean_grid, clean = _house()
    voxel_grid, partition = _house()
    k0 = 3 + 30                                                        # Fuge: Unterseite der oberen Decke
    partition.labels[20:80, 1:3, k0:k0 + 2] = -1                       # Rinne 2 Voxel breit, 2 tief, über der Krone
    voxel_grid.matrix[20:80, 1:3, k0:k0 + 2] = False
    level_joints(voxel_grid.matrix, partition.labels, [Joint(1, k0, np.ones(partition.labels.shape[:2], dtype=bool))],
                 leveling=2)
    assert (partition.labels == clean.labels).all() and (voxel_grid.matrix == clean_grid.matrix).all()
    plan, warnings = plan_connectors(voxel_grid, partition, CLEARANCE)
    assert not warnings and plan == plan_connectors(clean_grid, clean, CLEARANCE)[0]
    new, warnings = apply_connectors(_parts(voxel_grid, partition), {0: "unten", 1: "oben"}, plan, CLEARANCE)
    assert not warnings and all(m.is_watertight for m in new.values())


def test_too_narrow_wall_gives_warning():
    voxel_grid, partition = _house(wall=2)                             # Krone 0.8 mm < 1.2 mm
    plan, warnings = plan_connectors(voxel_grid, partition, CLEARANCE)
    assert plan == [] and warnings


def test_too_thin_slab_gives_warning():
    slab = int(MIN_ENGAGEMENT_MM / PEG_DEPTH_RATIO / PITCH)   # Zapfen wäre kürzer als MIN_ENGAGEMENT_MM
    voxel_grid, partition = _house(slab=slab)
    plan, warnings = plan_connectors(voxel_grid, partition, CLEARANCE)
    assert plan == [] and warnings


def test_stack_test_with_clearance():
    """Montiert durchdringen sich die Teile nicht, und um den Zapfen bleibt Luft (konisch, nur aufgelegt)."""
    voxel_grid, partition = _house()
    plan, _ = plan_connectors(voxel_grid, partition, CLEARANCE)
    new, _ = apply_connectors(_parts(voxel_grid, partition), {0: "unten", 1: "oben"}, plan, CLEARANCE)
    overlap_mesh = new["unten"].intersection(new["oben"], engine="manifold")
    assert abs(overlap_mesh.volume) < 0.01
    # um knapp das Spiel aufgeblähter Zapfen: noch immer keine Überschneidung → ringsum und oben bleibt Luft
    tight = CLEARANCE - 0.05
    thick = Connector(**{**plan[0].__dict__})
    thick.length += 2 * tight
    thick.width += 2 * tight
    thick.height += tight
    peg = geometry.peg(thick)
    assert abs(peg.intersection(new["oben"], engine="manifold").volume) < 0.01


def test_peg_tapers():
    voxel_grid, partition = _house()
    plan, _ = plan_connectors(voxel_grid, partition, CLEARANCE)
    z = geometry.peg(plan[0])
    v = z.vertices
    bottom = v[np.isclose(v[:, 2], v[:, 2].min())]
    top = v[np.isclose(v[:, 2], v[:, 2].max())]
    assert np.ptp(top[:, :2], axis=0).max() < np.ptp(bottom[:, :2], axis=0).max()
