"""Bereinigen der Teilzuordnung: Inseln, Kleinteile, hängende Stücke, Splitter.

Nach der Fugenzuordnung bleiben im Label-Gitter Reste, die sich nicht drucken lassen. Dieses Modul
ordnet sie dem Nachbarteil zu oder entfernt sie – und meldet jede Änderung als Warnung (keine stillen Fehler):
  * ``assign_islands``: abgetrennte kleine Stücke eines Teils gehen an das Nachbarteil mit der
    grössten Kontaktfläche (Gaubenwangen aufs Dach, Wandköpfe ans Geschoss darunter);
    winzige lose Splitter ohne Kontakt entfallen.
  * ``assign_small_pieces``: ganze Teile unter einem Mindestanteil gehen ans Nachbarteil.
  * ``assign_hanging``: Stücke, die unter die Unterseite ihres Teils ragen.
  * ``without_sliver``: lose Stücke einer Teil-Maske entfernen und geschlossene Hohlräume füllen.

Eingabe: Label-Gitter (Teilnummer je Voxel, −1 = leer)
Ausgabe: Label-Gitter wird verändert; Rückgabe ist die Anzahl umgehängter oder entfernter Stücke bzw. Warnungen
"""

import numpy as np
from scipy.ndimage import binary_dilation, find_objects, label

from config import ISLAND_RATIO, SLIVER_MAX_VOXELS, SMALL_PART_RATIO


def assign_hanging(labels: np.ndarray, count: int, max_voxel: int) -> int:
    """Gibt Stücke, die unter die Unterseite ihres Teils ragen, dem Nachbarteil (sonst: schneidet sie ab).

    Typisch: die letzten Stufen einer Treppe (Geschoss darunter), die in der Treppenöffnung
    der Decke tiefer liegen als die Unterseite des oberen Teils. Sie hingen unter der Bodenplatte
    und höben das Teil beim Drucken vom Bett ab. Je Teil zählt die häufigste unterste Schicht als
    Unterseite; Voxel darunter (höchstens ``max_voxel`` Schichten) gehen an das andere Teil mit
    den meisten Nachbarvoxeln, hängen sie an keinem, werden sie abgeschnitten.
    Betrifft nur die ersten ``count`` Teile (Geschosse), nicht die Dächer.
    """
    boxes = find_objects(labels + 1)
    reassigned = 0
    for number in range(count):
        if number >= len(boxes) or boxes[number] is None:     # Index w ↔ Label w (Werte sind um 1 verschoben)
            continue
        i, j, k = boxes[number]
        part = labels[i, j, k] == number
        bottom = np.where(part.any(axis=2), part.argmax(axis=2), -1)        # unterste Schicht je Spalte
        if not (bottom >= 0).any():
            continue
        usual_bottom = int(np.bincount(bottom[bottom >= 0]).argmax())        # häufigste Unterseite des Teils
        column_mask = (bottom >= 0) & (bottom < usual_bottom) & (usual_bottom - bottom <= max_voxel)
        layer_index = np.arange(part.shape[2])[None, None, :]
        hangs = part & column_mask[:, :, None] & (layer_index < usual_bottom)
        if not hangs.any():
            continue
        far = tuple(slice(max(0, s.start - 1), s.stop + 1) for s in (i, j, k))
        surroundings = labels[far]
        mask = np.zeros(surroundings.shape, dtype=bool)
        mask[i.start - far[0].start:i.start - far[0].start + hangs.shape[0],
              j.start - far[1].start:j.start - far[1].start + hangs.shape[1],
              k.start - far[2].start:k.start - far[2].start + hangs.shape[2]] = hangs
        neighbors = surroundings[binary_dilation(mask, structure=np.ones((3, 3, 3), dtype=bool)) & ~mask]
        neighbors = neighbors[(neighbors >= 0) & (neighbors != number)]
        labels[i, j, k][hangs] = np.bincount(neighbors).argmax() if len(neighbors) else -1   # ohne Nachbar: abschneiden
        reassigned += int(hangs.sum())
    return reassigned


def assign_islands(labels: np.ndarray, fraction: float = ISLAND_RATIO, sliver: int = SLIVER_MAX_VOXELS) -> int:
    """Gibt kleine abgetrennte Stücke eines Teils dem Nachbarteil mit der grössten Kontaktfläche.

    Je Label bleibt das grösste zusammenhängende Stück (Flächenkontakt); jedes andere,
    kleiner als ``fraction`` davon und mit Kontakt zu einem anderen Teil, wechselt. Stücke
    unter ``sliver`` Voxeln ohne jeden Kontakt (lose Splitter) werden gelöscht.
    Rückgabe: Anzahl umgehängter oder gelöschter Stücke.
    """
    switched = 0
    for value in [w for w in np.unique(labels) if w >= 0]:
        span_slices = find_objects((labels == value).astype(np.int8))[0]
        frame = tuple(slice(max(0, s.start - 1), s.stop + 1) for s in span_slices)
        part = labels[frame]
        fragments, n = label(part == value)
        if n < 2:
            continue
        sizes = np.bincount(fragments.ravel())[1:]
        main_component = int(np.argmax(sizes)) + 1
        for number, component_slice in enumerate(find_objects(fragments), start=1):
            if number == main_component or sizes[number - 1] >= fraction * sizes[main_component - 1]:
                continue
            near = tuple(slice(max(0, s.start - 1), s.stop + 1) for s in component_slice)
            fragment = fragments[near] == number
            margin = binary_dilation(fragment) & ~fragment
            neighbors = part[near][margin]
            neighbors = neighbors[(neighbors >= 0) & (neighbors != value)]
            if len(neighbors):
                part[near][fragment] = np.bincount(neighbors).argmax()
                switched += 1
            elif sizes[number - 1] < sliver and not (part[near][margin] == value).any():
                part[near][fragment] = -1
                switched += 1
    return switched


def assign_small_pieces(labels: np.ndarray, fraction: float = SMALL_PART_RATIO) -> int:
    """Ganze Teile unter ``fraction`` des Gesamtvolumens gehen ans Nachbarteil mit der grössten Kontaktfläche.

    Verhindert Restteile von wenigen Kubikmillimetern (z.B. ein Geschoss, von dem nach dem
    Zuordnen der Inseln fast nichts übrig blieb). Rückgabe: Anzahl aufgelöster Teile.
    """
    values, amounts = np.unique(labels[labels >= 0], return_counts=True)
    dissolved = 0
    for value, amount in sorted(zip(values, amounts), key=lambda t: t[1]):
        if amount >= fraction * amounts.sum():
            break
        span_slices = find_objects((labels == value).astype(np.int8))[0]
        near = tuple(slice(max(0, s.start - 1), s.stop + 1) for s in span_slices)
        part = labels[near] == value
        neighbors = labels[near][binary_dilation(part) & ~part]
        neighbors = neighbors[(neighbors >= 0) & (neighbors != value)]
        if len(neighbors):
            labels[near][part] = np.bincount(neighbors).argmax()
            dissolved += 1
    return dissolved


def assign_with_message(labels: np.ndarray, names: list[str], storey_count: int, max_hanging: int,
                          pitch: float) -> list[str]:
    """Inseln, Kleinteile und hängende Stücke zuordnen und jede Änderung als Warnung melden (keine stillen Fehler)."""
    def mm3(voxel: int) -> str:
        return f"{voxel * pitch ** 3:.0f} mm³"

    warnings = []
    empty_before = int((labels == -1).sum())
    fragments = assign_islands(labels)
    fragments += assign_islands(labels)   # zweite Runde: Stücke, die erst durch die erste Runde Nachbarn wurden
    sliver = int((labels == -1).sum()) - empty_before
    if fragments:
        text = f"{fragments} kleine abgetrennte Stücke dem Nachbarteil gegeben"
        if sliver:
            text += f", lose Splitter ohne Kontakt entfernt ({mm3(sliver)})"
        warnings.append(text + ".")
    previous = set(np.unique(labels[labels >= 0]).tolist())
    assign_small_pieces(labels)
    for value in sorted(previous - set(np.unique(labels[labels >= 0]).tolist())):
        warnings.append(f"Teil «{names[value]}» ist kleiner als {SMALL_PART_RATIO:.0%} des Modells "
                         "und wurde an das Nachbarteil angehängt (kein eigenes STL).")
    empty_before_hanging = int((labels == -1).sum())
    hanging = assign_hanging(labels, storey_count, max_hanging)
    trimmed = int((labels == -1).sum()) - empty_before_hanging
    if hanging:
        text = f"{mm3(hanging - trimmed)} unter der Unterseite eines Teils dem Nachbarteil gegeben"
        if trimmed:
            text += f", {mm3(trimmed)} ohne Nachbarteil abgeschnitten"
        warnings.append(text + ".")
    return warnings


def without_sliver(mask: np.ndarray, min_voxel: int, max_cavity: int = 0) -> tuple[np.ndarray, list[int], list[int]]:
    """Entfernt lose Stücke unter ``min_voxel`` (Flächenkontakt) und füllt geschlossene Hohlräume.

    Lose Stücke hängen nur über Kanten oder Ecken am Teil; Marching Cubes macht daraus winzige
    eigene Schalen. Sie hier im Gitter zu entfernen kostet Millisekunden – im fertigen Netz
    (``mesh.split``) war es der grösste Einzelposten der Erzeugung (NEST: 40 von 113 s).

    Gefüllt werden Hohlräume unter ``min_voxel`` (Vernetzungsreste) und solche bis ``max_cavity`` Voxel: Ein
    geschlossener Hohlraum (Schacht, Zwischenraum unter einem Bodenaufbau) ist nach dem Druck unsichtbar, bräuchte
    innen Stützen und wird im Slicer beim Trennen in Objekte zu einem Scheinkörper.
    Rückgabe: (Maske, Voxelzahl je gefülltem Hohlraum, Voxelzahl je verbleibendem), je nur ab ``min_voxel``.
    """
    if min_voxel <= 1 and not max_cavity:
        return mask, [], []
    if min_voxel > 1:
        fragments, n = label(mask)
        if n > 1:
            small = np.bincount(fragments.ravel()) < min_voxel
            small[0] = False
            if small.any():
                mask = mask & ~small[fragments]
    hollow, n = label(np.pad(~mask, 1, constant_values=True))      # Luft rundum: der Aussenraum hängt zusammen
    if n < 2:
        return mask, [], []
    sizes = np.bincount(hollow.ravel())
    inside = np.ones(len(sizes), dtype=bool)
    inside[[0, hollow[0, 0, 0]]] = False                          # Hintergrund und Aussenraum bleiben
    fill = inside & (sizes < max(min_voxel, max_cavity + 1))
    if fill.any():
        mask = mask | fill[hollow][1:-1, 1:-1, 1:-1]
    visible = sizes >= min_voxel
    return mask, sizes[fill & visible].tolist(), sizes[inside & ~fill & visible].tolist()
