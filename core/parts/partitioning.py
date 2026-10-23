"""Geschossweise Aufteilung des Gesamtmodells in druckbare Teile.

Das Gesamtmodell liegt in EINEM Voxelgitter. Jeder Voxel erhält ein Teil-Label
(Geschoss oder Dach); benachbarte Teile teilen sich dadurch exakt dieselben
Flächen – Voraussetzung für stapelbare Geschosse.

Ablauf (``partition_grid``):
  1. Fuge je Geschossgrenze finden und je Spalte glätten (core/parts/storey_joints.py).
  2. Dächer (core/parts/roof.py: geneigte Dachbauteile) erhalten ein eigenes Label.
  3. Inseln, Kleinteile und hängende Stücke dem Nachbarteil zuordnen (core/parts/cleanup.py).
Danach vernetzt ``mesh_pieces`` jedes Teil einzeln; die Anordnung auf dem Druckbett liegt in
core/parts/print_layout.py.

Eingabe: Voxelgitter, Geschosshöhen [(Name, Welt-Z)], optional Dach-Labels
Ausgabe: ``Partition`` (Label je Voxel, Teilnamen, Warnungen) bzw. ein wasserdichtes Mesh je Teil
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import trimesh
from scipy.ndimage import find_objects

from config import (CAVITY_FILL_RATIO, ROOF_MIN_RATIO, JOINT_OVERHANG_MM, SPECK_MIN_VOLUME_MM3, JOINT_LEVELING_MM,
                    JOINT_WIDTH_MM, JOINT_SLAB_MM)
from core.parts.cleanup import assign_with_message, without_sliver
from core.parts.storey_joints import cuts, joint_columns, smooth_joint, storey_and_above
from core.voxels.grid import VoxelGrid
from core.voxels.meshing import marching_cubes, postprocessed


@dataclass
class Partition:
    """Label je Voxel (−1 = leer) und Name je Label."""
    labels: np.ndarray
    names: list[str]
    warnings: list[str]
    mesh_names: dict[int, str] = field(default_factory=dict)   # Label → eindeutiger Name in mesh_pieces


def partition_grid(voxel_grid: VoxelGrid, storeys: list[tuple[str, float]], scale: int,
              floor_plans: dict[str, np.ndarray] | None = None, roof: np.ndarray | None = None,
              roof_names: list[str] | None = None) -> Partition:
    """Teilt das Gitter in Geschoss- und Dachteile (glättet dabei die Fugen in ``voxel_grid.matrix``).

    ``roof``: Label-Gitter der Dachbauteile (−1 = kein Dach, sonst Index in ``roof_names``).
    """
    floor_plans = storey_and_above(voxel_grid, storeys, floor_plans)
    ranges, warnings = cuts(voxel_grid, storeys, scale, floor_plans)
    m = voxel_grid.matrix
    voxel = 1000.0 / scale / voxel_grid.pitch                       # Voxel je realem Meter
    leveling = max(1, int(JOINT_LEVELING_MM / 1000 * voxel))
    plate = max(leveling + 1, int(round(JOINT_SLAB_MM / 1000 * voxel)))
    width = int(round(JOINT_WIDTH_MM / 1000 * voxel / 2))          # Radius der Öffnung: halbe Mindestbreite
    labels = np.zeros(m.shape, dtype=np.int16)
    k_index = np.arange(m.shape[2], dtype=np.int32)
    for i, (name, k, _) in enumerate(ranges[1:], start=1):
        height = smooth_joint(m, k, joint_columns(voxel_grid, floor_plans, name), leveling, plate, width)
        labels[k_index[None, None, :] >= height[:, :, None]] = i
    names = [name for name, _, _ in ranges]
    if roof is not None and roof_names:
        combined = max(1, int(m.sum()))
        for j, name in enumerate(roof_names):
            mask = (roof == j) & m
            if mask.sum() >= ROOF_MIN_RATIO * combined:
                labels[mask] = len(names)
                names.append(name)
    labels[~m] = -1
    warnings += assign_with_message(labels, names, len(ranges), max(1, int(JOINT_OVERHANG_MM / 1000 * voxel)),
                                       voxel_grid.pitch)
    return Partition(labels, names, warnings)


def mesh_pieces(voxel_grid: VoxelGrid, partition: Partition,
                progress: Callable[[str, int, int], None] | None = None) -> dict[str, trimesh.Trimesh]:
    """Ein wasserdichtes Mesh je Teil, von unten nach oben sortiert; leere Teile entfallen.

    Geschlossene Hohlräume bis CAVITY_FILL_RATIO des Teilvolumens werden gefüllt (core/parts/cleanup.without_sliver),
    grössere bleiben; beides meldet ``partition.warnings``.
    Teilnamen sind eindeutig (core.ifc.assignment.room_names); kämen trotzdem zwei gleich vor,
    erhält das zweite eine Nummer, statt das erste still zu überschreiben.
    """
    result = []
    boxes = find_objects(partition.labels + 1)       # Box je Label in EINEM Durchgang: Index w ↔ Label w (−1 = leer)
    values = [w for w in range(len(partition.names)) if w < len(boxes) and boxes[w] is not None]
    min_voxel = int(np.ceil(SPECK_MIN_VOLUME_MM3 / voxel_grid.pitch ** 3))
    mm3 = voxel_grid.pitch ** 3
    for number, value in enumerate(values, start=1):
        span_slices = boxes[value]
        mask = partition.labels[span_slices] == value
        mask, filled, kept = without_sliver(mask, min_voxel, int(CAVITY_FILL_RATIO * mask.sum()))
        if not mask.any():                                        # Teil bestand nur aus Krumen
            continue
        name = partition.names[value]
        if filled:
            partition.warnings.append(f"«{name}»: geschlossene Hohlräume gefüllt ({len(filled)}, {sum(filled) * mm3:.0f} mm³) "
                                      "– unsichtbar, sonst bräuchten sie innen Stützen und wären im Slicer eigene Objekte.")
        if kept:
            partition.warnings.append(f"«{name}»: grosse geschlossene Hohlräume bleiben ({len(kept)}, {sum(kept) * mm3:.0f} mm³) "
                                      "– im Slicer das Teil nicht in Objekte trennen.")
        lo = np.array([s.start for s in span_slices])
        mesh = postprocessed(marching_cubes(mask, voxel_grid.origin + lo * voxel_grid.pitch, voxel_grid.pitch), specks=False)
        result.append((lo[2], partition.names[value], mesh, value))
        if progress:
            progress(partition.names[value], number, len(values))
    parts: dict[str, trimesh.Trimesh] = {}
    partition.mesh_names = {}
    for _, name, mesh, value in sorted(result, key=lambda t: t[0]):
        unique_name, i = name, 1
        while unique_name in parts:
            i += 1
            unique_name = f"{name} #{i}"
        parts[unique_name] = mesh
        partition.mesh_names[value] = unique_name
    return parts
