"""Tests für core/voxels/alignment: dominante Wandrichtung erkennen und zurückdrehen."""

import numpy as np
import pytest
import trimesh

from core.voxels.alignment import main_angle, rotation


def _wall(length, angle_deg, offset=(0, 0)):
    w = trimesh.creation.box(extents=(length, 2, 30))
    w.apply_transform(trimesh.transformations.rotation_matrix(np.radians(angle_deg), [0, 0, 1]))
    return w.apply_translation([*offset, 15])


@pytest.mark.parametrize("angle", [0.0, 23.0, -17.5, 44.0, 67.0])
def test_detects_the_rotation_angle(angle):
    """Rechtwinkliges Gebäude, um «winkel» gedreht → Ergebnis modulo 90° in −45…45."""
    meshes = [_wall(80, angle), _wall(50, angle + 90, (10, 10)), _wall(60, angle, (0, 40))]
    expected = (angle + 45) % 90 - 45
    assert main_angle(meshes) == pytest.approx(expected, abs=0.05)


def test_dominant_system_wins():
    """Ein kleiner, schräger Flügel ändert die Hauptrichtung nicht."""
    meshes = [_wall(100, 12.0), _wall(80, 102.0, (20, 0)), _wall(20, 40.0, (60, 60))]
    assert main_angle(meshes) == pytest.approx(12.0, abs=0.1)


def test_without_vertical_faces():
    plate = trimesh.creation.box(extents=(50, 50, 0.0))
    plate.faces = plate.faces[np.abs(plate.face_normals[:, 2]) > 0.9]
    assert main_angle([plate]) == 0.0
    assert main_angle([]) == 0.0


def test_rotation_makes_walls_axis_parallel():
    wall = _wall(80, 23.0, (500, 300))
    straight = wall.copy().apply_transform(rotation(23.0, (500, 300)))
    assert np.sort(straight.extents)[:2] == pytest.approx([2, 30], abs=1e-6)   # wieder 80 × 2 × 30
    assert straight.bounds.mean(axis=0)[:2] == pytest.approx([500, 300])       # um die Mitte gedreht
