"""Ganze Bauteile einem Teil geben: Dächer, Decken und Deckel.

Die Fugenebenen (core/parts/partitioning.py) schneiden nur, was mehrere Geschosse durchläuft: Wände, Stützen,
Fassaden, Treppen. Dächer und waagrechte Platten (Decken, Dachplatten, Beläge) werden nie zerschnitten – das
Gitter weiss je Voxel, zu welchem Bauteil er gehört (``VoxelGrid.owner``), und dieses Modul gibt jedes solche
Bauteil als Ganzes einem Teil:

  * Dach: Alle Voxel eines Dachteils («Dach <Geschoss>», core/parts/roof.py) werden ein eigenes Teil, je
    zusammenhängendem Stück. Ein niedriges «Dach» (Vordach, Terrassenbelag, flacher als ROOF_ZONE_MIN_HEIGHT_MM)
    ist keine Dachschale und wird wie eine Decke behandelt.
  * Decke: Eine waagrechte Platte gehört ganz zu dem Geschoss, in dem der grösste Teil ihrer Voxel liegt – die Decke
    an der Fuge liegt über der Fuge und ist der Boden des Teils darüber. Nur was von einer solchen Decke mehr als
    JOINT_LEVELING_MM unter die Fuge reicht (dickerer Deckenbereich), bleibt beim Geschoss darunter: Die Fuge bleibt eben.
    Eine geneigte Decke über Räumen, die eine Fuge kreuzt, bleibt als Deckel ganz.
  * Aufliegend: Liegt eine Platte mit weniger als LID_MIN_CLEARANCE_MM Luft auf einem anderen Teil (Belag auf einem
    Deckel, Dämmung unter der Decke des Geschosses darüber), geht sie mit ihm.
  * Deckel: Eine Decke, die über Räumen ihres eigenen Teils liegt und auf nichts aufliegt (tiefer liegende
    Terrasse, Flachdach eines Gebäudes ohne Dachgeschoss, TG-Decke neben dem Haus), würde im Druck Stützen in den
    Räumen brauchen. Sie wird ein eigenes Teil «Decke <Geschoss>» (im obersten Geschoss «Dach <Geschoss>») und liegt
    flach auf dem Bett. Aufbauten darauf (Brüstung, Geländer) folgen ihr (core/parts/cleanup.assign_by_support).

Eingabe: Label-Gitter nach den Fugenebenen, Teilnamen, Voxelgitter mit ``owner``, Fugen
Ausgabe: Label-Gitter und Teilnamen werden ergänzt
"""

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import find_objects, label

from config import LID_ATTACHED_RATIO, LID_MIN_AREA_M2, LID_MIN_BELOW_RATIO, LID_MIN_CLEARANCE_MM, ROOF_ZONE_MIN_HEIGHT_MM
from core.parts.storey_joints import Joint
from core.voxels.grid import VoxelGrid


@dataclass
class _Piece:
    """Die Voxel eines Bauteils im Gitter: Ausschnitt (Box) und Maske darin."""
    box: tuple[slice, slice, slice]
    mask: np.ndarray

    @property
    def bottom(self) -> int:
        return self.box[2].start + int(np.flatnonzero(self.mask.any(axis=(0, 1)))[0])


def horizontal_mask(voxel_grid: VoxelGrid) -> np.ndarray | None:
    """Bool-Gitter: Voxel gehört einer waagrechten Platte (None ohne Bauteil-Zuordnung)."""
    if voxel_grid.owner is None or not voxel_grid.owners:
        return None
    flags = np.array([o.horizontal for o in voxel_grid.owners] + [False])      # Index −1 → False
    return flags[voxel_grid.owner]


def assign_whole_elements(labels: np.ndarray, names: list[str], voxel_grid: VoxelGrid, joints: list[Joint],
                          voxel_per_m: float, leveling: int, horizontal_voxels: np.ndarray | None = None) -> None:
    """Dächer als eigene Teile, waagrechte Platten ganz an ein Geschoss, Deckel als eigene Teile (siehe Modul-Doku).

    ``leveling``: so viele Voxel darf die Unterseite einer Decke an der Fuge tiefer liegen als die Fuge
    (level_joints schneidet das ab); was tiefer reicht, bleibt beim Geschoss darunter, damit die Fuge eben ist.
    ``horizontal_voxels``: ``horizontal_mask(voxel_grid)``, falls schon berechnet.
    """
    if horizontal_voxels is None:
        horizontal_voxels = horizontal_mask(voxel_grid)
    if horizontal_voxels is None:
        return
    storey_count = len(names)
    min_voxels = int(LID_MIN_AREA_M2 * voxel_per_m ** 2)       # eine Schicht der kleinsten Deckelfläche
    clearance = max(1, int(round(LID_MIN_CLEARANCE_MM / 1000 * voxel_per_m)))
    roofs: dict[str, list[_Piece]] = {}
    horizontal: list[_Piece] = []
    boxes = find_objects(voxel_grid.owner + 1)                   # Index w ↔ Bauteil w (Werte sind um 1 verschoben)
    for index, owner in enumerate(voxel_grid.owners):
        if index >= len(boxes) or boxes[index] is None:
            continue
        box = boxes[index]
        mask = (voxel_grid.owner[box] == index) & (labels[box] >= 0)
        if not mask.any():
            continue
        if owner.roof:
            roofs.setdefault(owner.roof, []).append(_Piece(box, mask))
        elif owner.horizontal:
            horizontal.append(_Piece(box, mask))
    min_height = ROOF_ZONE_MIN_HEIGHT_MM / 1000 * voxel_per_m
    for name, pieces in roofs.items():
        full = _union(pieces, labels.shape)
        layers = np.flatnonzero(full.any(axis=(0, 1)))
        if layers[-1] - layers[0] + 1 < min_height:               # Vordach, Terrassenbelag: wie eine Decke behandeln
            horizontal += pieces
            continue
        _label_components(labels, names, full, name, min_voxels)
    horizontal.sort(key=lambda piece: piece.bottom)              # von unten nach oben: was darunter liegt, hat sein Label
    plane: list[np.ndarray] = []                                 # Label je Voxel nach den Fugenebenen, je Platte
    for piece in horizontal:
        values = labels[piece.box][piece.mask]
        plane.append(values)
        labels[piece.box][piece.mask] = np.bincount(values).argmax()   # das Geschoss, in dem der grösste Teil der Platte liegt
    lids: dict[int, int] = {}                                    # Geschoss → vorläufiges Deckel-Label (Stücke am Ende)
    lid_masks: dict[int, np.ndarray] = {}                        # Deckel-Label → Voxel der Deckelplatten selbst
    attached: list[_Piece] = []                                  # Platten, die auf einem anderen Teil aufliegen
    k_joint = {joint.label: joint.k for joint in joints}
    for piece, plane_values in zip(horizontal, plane):
        value = int(labels[piece.box][piece.mask][0])
        if value >= storey_count:                                 # liegt schon auf einem Dach- oder Deckel-Label
            continue
        beneath = _neighbour_labels(labels, piece, -1, clearance)
        if (resting := _resting_on(beneath, value)) is not None:  # liegt auf einem anderen Teil auf → geht mit ihm
            labels[piece.box][piece.mask] = resting
            attached.append(piece)
        elif (resting := _resting_on(_neighbour_labels(labels, piece, +1, clearance), value)) is not None:
            labels[piece.box][piece.mask] = resting              # hängt unter einem anderen Teil (Dämmung unter der Decke)
            attached.append(piece)
        elif _is_lid(labels, horizontal_voxels, piece, value, beneath, joints, min_voxels):
            # sofort umbenennen: Ein Belag mit Luftspalt darüber sieht den Deckel dann als anderes Teil («aufliegend»)
            if value not in lids:
                lids[value] = len(names)
                names.append(f"{'Dach' if value == storey_count - 1 else 'Decke'} {names[value]}")
            labels[piece.box][piece.mask] = lids[value]
            lid_masks.setdefault(lids[value], np.zeros(labels.shape, dtype=bool))[piece.box] |= piece.mask
        elif value in k_joint:
            # Decke an der Fuge: Was tiefer als ``leveling`` unter die Fuge reicht (dickerer Deckenbereich, Unterzug in der
            # Decke), bleibt beim Geschoss darunter – die Fuge bleibt eben, beide Teile liegen flach auf dem Bett.
            k_voxel = np.nonzero(piece.mask)[2] + piece.box[2].start
            deep = (k_voxel < k_joint[value] - leveling) & (plane_values < value)
            if deep.any():
                target = labels[piece.box]
                cells = tuple(index[deep] for index in np.nonzero(piece.mask))
                target[cells] = plane_values[deep]
    for value, lid in lids.items():                               # getrennte Deckel eines Geschosses: je ein Teil
        components, n = label(lid_masks[lid])
        sizes = np.bincount(components.ravel())
        for number in range(1, n + 1):
            if sizes[number] < min_voxels:
                labels[components == number] = value               # zu klein für ein eigenes Teil: zurück ans Geschoss
            elif number > 1:
                labels[components == number] = len(names)
                names.append(names[lid])
    if len(names) > storey_count + len(lids):                    # aufliegende Platten folgen dem Stück unter bzw. über ihnen
        for piece in attached:
            below = _neighbour_labels(labels, piece, -1, clearance)
            above = _neighbour_labels(labels, piece, +1, clearance)
            value = int(labels[piece.box][piece.mask][0])
            if (resting := _resting_on(below, -1)) is not None or (resting := _resting_on(above, -1)) is not None:
                if resting != value:
                    labels[piece.box][piece.mask] = resting


def _union(pieces: list[_Piece], shape: tuple) -> np.ndarray:
    full = np.zeros(shape, dtype=bool)
    for piece in pieces:
        full[piece.box] |= piece.mask
    return full


def _neighbour_labels(labels: np.ndarray, piece: _Piece, direction: int, depth: int) -> np.ndarray:
    """Je Spalte des Grundrisses das erste Teil unter (−1) bzw. über (+1) der Platte, höchstens ``depth`` Voxel Luft
    entfernt (−1 = nur Luft)."""
    i, j, k = piece.box
    footprint = piece.mask.any(axis=2)
    ii, jj = np.nonzero(footprint)
    if direction < 0:
        edge = piece.mask.argmax(axis=2)[footprint] + k.start                        # unterste Schicht
    else:
        edge = piece.mask.shape[2] - 1 - piece.mask[:, :, ::-1].argmax(axis=2)[footprint] + k.start   # oberste
    ii, jj = ii + i.start, jj + j.start
    result = np.full(len(ii), -1, dtype=labels.dtype)
    open_columns = np.ones(len(ii), dtype=bool)
    for d in range(1, depth + 1):
        kk = edge + direction * d
        valid = open_columns & (kk >= 0) & (kk < labels.shape[2])
        if not valid.any():
            break
        found = labels[ii[valid], jj[valid], kk[valid]]
        hit = found >= 0
        index = np.flatnonzero(valid)[hit]
        result[index] = found[hit]
        open_columns[index] = False
    return result


def _resting_on(neighbours: np.ndarray, own: int) -> int | None:
    """Das andere Teil, auf dem die Platte in mindestens LID_ATTACHED_RATIO ihrer Spalten aufliegt, sonst None."""
    others = neighbours[(neighbours >= 0) & (neighbours != own)]
    if len(neighbours) and len(others) >= LID_ATTACHED_RATIO * len(neighbours):
        return int(np.bincount(others).argmax())
    return None


def _is_lid(labels: np.ndarray, horizontal: np.ndarray, piece: _Piece, value: int, beneath: np.ndarray,
            joints: list[Joint], min_voxels: int) -> bool:
    """Deckel: gross genug, liegt kaum auf dem eigenen Teil auf, aber über Räumen des eigenen Teils.

    «Über Räumen»: In genügend Spalten des Grundrisses steht zwischen der Fuge des Teils und der Platte etwas vom Teil,
    das keine Platte ist (Wände, Stützen). Eine Decke an der Fuge hat darunter nur das Teil darunter → kein Deckel;
    eine Decke, die neben einer dickeren Nachbardecke liegt, auch nicht.
    """
    if len(beneath) < min_voxels:
        return False
    if (beneath == value).sum() >= LID_ATTACHED_RATIO * len(beneath):
        return False
    i, j, k = piece.box
    k_joint = next((joint.k for joint in joints if joint.label == value), 0)
    footprint = piece.mask.any(axis=2)
    bottom = piece.mask.argmax(axis=2) + k.start                 # unterste Schicht der Platte je Spalte (global)
    stop = int(bottom[footprint].max())
    if stop <= k_joint:
        return False
    column = (labels[i, j, k_joint:stop] == value) & ~horizontal[i, j, k_joint:stop]
    layer = np.arange(k_joint, stop)[None, None, :]
    below = (column & (layer < bottom[:, :, None])).any(axis=2) & footprint
    return below.sum() >= LID_MIN_BELOW_RATIO * footprint.sum()


def _label_components(labels: np.ndarray, names: list[str], mask: np.ndarray, name: str, min_voxels: int) -> None:
    """Jedes zusammenhängende Stück der Maske ab ``min_voxels`` wird ein eigenes Teil ``name`` (Namen macht
    mesh_pieces eindeutig); kleinere Stücke (auch Dachstücke) behalten ihr Label und folgen ihrer Auflage."""
    components, n = label(mask)
    sizes = np.bincount(components.ravel())
    for number in range(1, n + 1):
        if sizes[number] >= min_voxels:
            labels[components == number] = len(names)
            names.append(name)
