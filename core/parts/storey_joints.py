"""Fugen zwischen den Geschossen: Höhe finden und die Fuge eben halten.

Zwischen zwei Geschossteilen liegt eine Fuge. Ihre Höhe entsteht in zwei Schritten:
  1. ``cuts``: Fuge je Geschossgrenze = Deckenunterkante im Suchfenster um die Geschoss-Z,
     gezählt nur dort, wo dieses oder ein höheres Geschoss steht (Grundrisse seiner
     IFC-Bauteile). Ausserhalb gibt es keine Fuge – ein tieferer Gebäudeflügel wird
     nicht von der Fuge eines höheren geschnitten.
  2. ``level_joints``: Nachdem die Aufteilung (core/parts/partitioning.py) jedem Voxel sein Teil gegeben hat, wird
     die Fuge je Spalte eben gehalten: Kleine Absätze des oberen Teils unter der Fuge (Dämmung unter der Decke,
     eine Decke, deren Unterseite ein Voxel tiefer liegt) werden abgeschnitten, kleine Rücksprünge darüber
     aufgefüllt → die Unterseite des oberen Teils ist eben und steht auf dem Bett wie auf dem Teil darunter.

Falle (verifiziert am NEST-Modell): ``IfcBuildingStorey.Elevation`` ist relativ
(EG = 0.0, Wände aber ab 432.6 m Welt-Z). Die Fugenhöhe kommt deshalb aus der
ObjectPlacement im Weltsystem (``storey_heights``).

Eingabe: Voxelgitter, Geschosshöhen [(Name, Welt-Z)], Grundrisse je Geschoss
Ausgabe: Schichtbereich [k_from, k_to) je Geschoss (``cuts``); ``level_joints`` verändert Gitter und Labels
"""

from typing import NamedTuple

import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np

from config import JOINT_MIN_RISE, JOINT_SEARCH_WINDOW_ABOVE_M, JOINT_SEARCH_WINDOW_BELOW_M
from core.ifc.assignment import room_names
from core.voxels.grid import VoxelGrid


class Joint(NamedTuple):
    """Fuge unter einem Geschossteil: sein Label, die Schicht k und die Spalten, in denen die Fuge gilt."""
    label: int
    k: int
    columns: np.ndarray


def storey_heights(model: ifcopenshell.file, scale: int) -> list[tuple[str, float]]:
    """(eindeutiger Name, Welt-Z im Modellmass [mm]) je IfcBuildingStorey, aufsteigend."""
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(model)   # Projekteinheit → m
    names = room_names(model)
    heights = []
    for s in model.by_type("IfcBuildingStorey"):
        if s.ObjectPlacement is None:
            continue
        z = ifcopenshell.util.placement.get_local_placement(s.ObjectPlacement)[2, 3]
        heights.append((names[s.id()], float(z) * unit_scale * 1000.0 / scale))
    return sorted(heights, key=lambda h: h[1])


def cuts(voxel_grid: VoxelGrid, storeys: list[tuple[str, float]], scale: int,
             floor_plans: dict[str, np.ndarray] | None = None) -> tuple[list[tuple[str, int, int]], list[str]]:
    """Z-Schichtbereich [k_from, k_to) je Geschoss (Fugenebenen) und Warnungen.

    Die Fuge unter Geschoss n liegt im Suchfenster um seine Z-Höhe dort, wo die
    Voxelzahl je Schicht am stärksten ansteigt (= Unterkante der Decke). Mit
    ``floor_plans`` (Geschoss → 2D-Maske) zählen nur die Spalten im Grundriss von n.
    """
    if len(storeys) < 2:
        return [(storeys[0][0] if storeys else "Modell", 0, voxel_grid.matrix.shape[2])], []

    nz = voxel_grid.matrix.shape[2]

    def layer_index(z_mm: float) -> int:
        return int(round((z_mm - voxel_grid.origin[2]) / voxel_grid.pitch))

    boundaries, warnings = [0], []
    for name, z in storeys[1:]:
        columns = joint_columns(voxel_grid, floor_plans, name)
        per_layer = voxel_grid.matrix[columns].sum(axis=0).astype(np.int64)
        base_area = max(1, int(voxel_grid.matrix[columns].any(axis=1).sum()))
        start_idx = max(1, layer_index(z - JOINT_SEARCH_WINDOW_BELOW_M * 1000 / scale))
        stop_idx = min(nz - 1, layer_index(z + JOINT_SEARCH_WINDOW_ABOVE_M * 1000 / scale))
        cut = layer_index(z)
        if stop_idx > start_idx:
            rise = per_layer[start_idx:stop_idx + 1] - per_layer[start_idx - 1:stop_idx]
            j = int(np.argmax(rise))
            if rise[j] >= JOINT_MIN_RISE * base_area:
                cut = start_idx + j
            else:
                warnings.append(f"Fuge bei «{name}»: keine klare Deckenunterkante – Schnitt auf Geschoss-Z.")
        boundaries.append(min(max(cut, boundaries[-1] + 1), nz - 1))
    boundaries.append(nz)
    ranges = [(name, boundaries[i], boundaries[i + 1]) for i, (name, _) in enumerate(storeys)]
    return ranges, warnings


def joint_columns(voxel_grid: VoxelGrid, floor_plans: dict[str, np.ndarray] | None, name: str) -> np.ndarray:
    """2D-Maske der Spalten, in denen die Fuge des Geschosses gilt (ohne Angabe: überall)."""
    g = (floor_plans or {}).get(name)
    return g if g is not None and g.any() else np.ones(voxel_grid.matrix.shape[:2], dtype=bool)


def storey_and_above(voxel_grid: VoxelGrid, storeys: list[tuple[str, float]],
                 floor_plans: dict[str, np.ndarray] | None) -> dict[str, np.ndarray] | None:
    """Je Geschoss die Spalten, in denen es ODER ein höheres Geschoss steht (dort gilt seine Fuge)."""
    if not floor_plans:
        return None
    union_mask = np.zeros(voxel_grid.matrix.shape[:2], dtype=bool)
    result = {}
    for name, _ in reversed(storeys):
        if (g := floor_plans.get(name)) is not None:
            union_mask = union_mask | g
        result[name] = union_mask.copy()
    return result


def level_joints(m: np.ndarray, labels: np.ndarray, joints: list[Joint], leveling: int) -> None:
    """Hält jede Fuge eben (verändert ``m`` und ``labels``). Zahlen in Voxeln.

    In den Spalten der Fuge gilt für das Teil darüber:
      * Voxel des Teils bis ``leveling`` unter der Fuge (Dämmung unter der Decke, eine Decke, deren Unterseite ein
        Voxel tiefer liegt) werden entfernt – sonst stünde das Teil auf dem Absatz statt auf seiner Unterseite.
      * Ist die Fuge leer und beginnt das Teil höchstens ``leveling`` darüber (Decke dort dünner), wird bis zur
        Fuge aufgefüllt – sonst hinge die Unterseite dort in der Luft.
    Dächer, Deckel und das Teil darunter bleiben unberührt: Nur Voxel mit dem Label des oberen Teils ändern sich.
    """
    nz = m.shape[2]
    for joint in joints:
        value, k, columns = joint
        for d in range(1, leveling + 1):
            if k - d >= 0:
                trim = columns & (labels[:, :, k - d] == value)
                labels[:, :, k - d][trim] = -1
                m[:, :, k - d][trim] = False
        gap = _run_length(~m, k, 1, leveling + 1)
        start = np.minimum(k + gap, nz - 1)
        starts_here = np.take_along_axis(labels, start[:, :, None], axis=2)[:, :, 0] == value
        fill_up = columns & ~m[:, :, k] & (gap <= leveling) & (k + gap < nz) & starts_here
        for d in range(leveling):
            if k + d < nz:
                selected = fill_up & (gap > d)
                m[:, :, k + d] |= selected
                labels[:, :, k + d][selected] = value


def _run_length(m: np.ndarray, start: int, step: int, n: int) -> np.ndarray:
    """Je Spalte: Anzahl aufeinanderfolgender True ab Schicht ``start`` in Richtung ``step`` (max. n)."""
    tally = np.zeros(m.shape[:2], dtype=np.int32)
    running = np.ones(m.shape[:2], dtype=bool)
    for d in range(n):
        k = start + step * d
        if not 0 <= k < m.shape[2]:
            break
        running &= m[:, :, k]
        tally += running
    return tally
