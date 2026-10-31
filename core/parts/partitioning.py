"""Geschossweise Aufteilung des Gesamtmodells in druckbare Teile.

Das Gesamtmodell liegt in EINEM Voxelgitter. Jeder Voxel erhält ein Teil-Label
(Geschoss, Dach oder Deckel); benachbarte Teile teilen sich dadurch exakt dieselben
Flächen – Voraussetzung für stapelbare Geschosse.

Ablauf (``partition_grid``):
  1. Fuge je Geschossgrenze finden (core/parts/storey_joints.cuts); alles über der Fuge gehört zum Geschoss darüber –
     das schneidet, was mehrere Geschosse durchläuft (Wände, Stützen, Fassaden, Treppen), je Spalte an der Unterseite
     der Decke darüber.
  2. Dächer und waagrechte Platten werden nie zerschnitten: Sie gehen als Ganzes an ein Teil, Dächer und Deckel
     (Decken über Räumen ohne Auflage) werden eigene Teile (core/parts/ownership.py).
  3. Abgetrennte Stücke dem Teil geben, auf dem sie stehen; Kleinteile ans Nachbarteil (core/parts/cleanup.py).
  4. Zuletzt die Fugen eben halten: kleine Absätze unter der Fuge abschneiden, Rücksprünge darüber auffüllen
     (storey_joints.level_joints) – so steht jedes Geschossteil mit seiner Fuge auf dem Bett.
Danach vernetzt ``mesh_pieces`` jedes Teil einzeln; die Anordnung auf dem Druckbett liegt in
core/parts/print_layout.py.

Eingabe: Voxelgitter (mit Bauteil je Voxel), Geschosshöhen [(Name, Welt-Z)], Grundrisse je Geschoss
Ausgabe: ``Partition`` (Label je Voxel, Teilnamen, Warnungen) bzw. ein wasserdichtes Mesh je Teil
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import trimesh
from scipy.ndimage import find_objects

from config import CAVITY_FILL_RATIO, JOINT_LEVELING_MM, JOINT_SLAB_MAX_MM, SPECK_MIN_VOLUME_MM3
from core.parts.cleanup import assign_with_message, without_sliver
from core.parts.ownership import assign_whole_elements, horizontal_mask
from core.parts.storey_joints import cuts, Joint, joint_columns, level_joints, storey_and_above
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
              floor_plans: dict[str, np.ndarray] | None = None) -> Partition:
    """Teilt das Gitter in Geschoss-, Dach- und Deckelteile (hält dabei die Fugen in ``voxel_grid.matrix`` eben)."""
    floor_plans = storey_and_above(voxel_grid, storeys, floor_plans)
    ranges, warnings = cuts(voxel_grid, storeys, scale, floor_plans)
    m = voxel_grid.matrix
    voxel_per_m = 1000.0 / scale / voxel_grid.pitch                 # Voxel je realem Meter
    leveling = max(1, int(JOINT_LEVELING_MM / 1000 * voxel_per_m))
    # Spalten ausserhalb aller Grundrisse (Bauteile ohne Geschoss, Ränder unter dem Dach): dort gilt jede Fuge.
    # Sonst fielen sie ans unterste Geschoss – auch weit über dessen Decke.
    outside = ~floor_plans[storeys[0][0]] if floor_plans and storeys else np.zeros(m.shape[:2], dtype=bool)
    labels = np.zeros(m.shape, dtype=np.int16)
    k_index = np.arange(m.shape[2], dtype=np.int32)
    horizontal = horizontal_mask(voxel_grid)
    slab_window = max(1, int(round(JOINT_SLAB_MAX_MM / 1000 * voxel_per_m)))
    joints = []
    for i, (name, k, _) in enumerate(ranges[1:], start=1):
        columns = joint_columns(voxel_grid, floor_plans, name) | outside
        # Wände, Stützen, Treppen werden je Spalte an der Unterseite der Decke darüber geschnitten: Wo die Decke dünner
        # ist als an der Fuge, bleibt der Wandkopf darunter beim Geschoss darunter. Ohne Decke in der Spalte gilt k.
        cut = np.full(m.shape[:2], k, dtype=np.int32)
        if horizontal is not None:
            floor = horizontal[:, :, k:k + slab_window] & m[:, :, k:k + slab_window]
            has_floor = floor.any(axis=2)
            cut[has_floor] = k + floor.argmax(axis=2)[has_floor]
            labels[(k_index[None, None, :] >= k) & columns[:, :, None] & horizontal] = i
            labels[(k_index[None, None, :] >= cut[:, :, None]) & columns[:, :, None] & ~horizontal] = i
        else:
            labels[(k_index[None, None, :] >= k) & columns[:, :, None]] = i
        joints.append(Joint(i, k, columns))
    labels[~m] = -1
    names = [name for name, _, _ in ranges]
    assign_whole_elements(labels, names, voxel_grid, joints, voxel_per_m, leveling, horizontal)
    warnings += assign_with_message(labels, names, len(ranges), voxel_grid.pitch)
    level_joints(m, labels, joints, leveling)      # zuletzt: danach ändert nichts mehr die Unterseite eines Teils
    return Partition(labels, names, warnings)


def mesh_pieces(voxel_grid: VoxelGrid, partition: Partition,
                progress: Callable[[str, int, int], None] | None = None) -> dict[str, trimesh.Trimesh]:
    """Ein wasserdichtes Mesh je Teil, von unten nach oben sortiert; leere Teile entfallen.

    Geschlossene Hohlräume bis CAVITY_FILL_RATIO des Teilvolumens werden gefüllt (core/parts/cleanup.without_sliver),
    grössere bleiben; beides meldet ``partition.warnings``.
    Teilnamen sind eindeutig (core.ifc.assignment.room_names); kommen trotzdem zwei gleich vor (zwei Deckel eines
    Geschosses), erhält das zweite eine Nummer, statt das erste still zu überschreiben.
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
        mesh = postprocessed(marching_cubes(voxel_grid.scalar_field(mask, lo), voxel_grid.origin + lo * voxel_grid.pitch, voxel_grid.pitch), specks=False)
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
