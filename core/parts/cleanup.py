"""Bereinigen der Teilzuordnung: Stücke ohne Auflage, Kleinteile, Splitter.

Nach der Zuordnung bleiben im Label-Gitter Stücke, die sich so nicht drucken lassen. Dieses Modul
ordnet sie dem Teil zu, das sie trägt, oder entfernt sie – und meldet jede Änderung als Warnung (keine stillen Fehler):
  * ``assign_by_support``: Ein abgetrenntes Stück eines Teils (es hängt nicht am Hauptstück) geht an das Teil, auf dem
    es steht (Voxel direkt unter seinen untersten Voxeln): Brüstungen und Dachaufbauten aufs Dach, Gaubenwangen aufs
    Dach, Treppenstufen in der Deckenöffnung ans Geschoss darunter, ein Geländerband auf eine Terrasse. Steht es
    auf nichts, zählt das Teil mit dem meisten seitlichen Kontakt; winzige Splitter ohne jeden Kontakt entfallen.
  * ``assign_small_pieces``: ganze Geschossteile unter einem Mindestanteil gehen ans Nachbarteil.
  * ``without_sliver``: lose Stücke einer Teil-Maske entfernen und geschlossene Hohlräume füllen.

Eingabe: Label-Gitter (Teilnummer je Voxel, −1 = leer)
Ausgabe: Label-Gitter wird verändert; Rückgabe ist die Anzahl umgehängter oder entfernter Stücke bzw. Warnungen
"""

import numpy as np
from scipy.ndimage import binary_dilation, find_objects, label

from config import SLIVER_MAX_VOXELS, SMALL_PART_RATIO


def assign_by_support(labels: np.ndarray, sliver: int = SLIVER_MAX_VOXELS) -> tuple[int, int]:
    """Gibt abgetrennte Stücke eines Teils dem Teil, auf dem sie stehen.

    Je Label bleibt das grösste zusammenhängende Stück (Flächenkontakt). Jedes andere wechselt zu dem Teil, das
    am häufigsten direkt unter seinen untersten Voxeln liegt; liegt dort kein anderes Teil, zu dem mit dem meisten
    Kontakt ringsum. Stücke unter ``sliver`` Voxeln ohne jeden Kontakt (lose Splitter) werden gelöscht.
    Rückgabe: (Anzahl umgehängter Stücke, Anzahl gelöschter Voxel).
    """
    switched = deleted = 0
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
            if number == main_component:
                continue
            near = tuple(slice(max(0, s.start - 1), s.stop + 1) for s in component_slice)
            fragment = fragments[near] == number
            below = np.zeros_like(fragment)
            below[:, :, :-1] = fragment[:, :, 1:]                  # die Voxel direkt unter dem Stück
            below &= ~fragment
            neighbors = _other_parts(part[near][below], value)
            margin = binary_dilation(fragment) & ~fragment
            if not len(neighbors):
                above = np.zeros_like(fragment)
                above[:, :, 1:] = fragment[:, :, :-1]               # was auf dem Stück liegt, trägt es nicht
                neighbors = _other_parts(part[near][margin & ~above], value)
            if len(neighbors):
                part[near][fragment] = np.bincount(neighbors).argmax()
                switched += 1
            elif sizes[number - 1] < sliver and not (part[near][margin] == value).any():
                part[near][fragment] = -1
                deleted += int(sizes[number - 1])
    return switched, deleted


def _other_parts(values: np.ndarray, own: int) -> np.ndarray:
    return values[(values >= 0) & (values != own)]


def assign_small_pieces(labels: np.ndarray, count: int | None = None, fraction: float = SMALL_PART_RATIO) -> int:
    """Ganze Teile unter ``fraction`` des Gesamtvolumens gehen ans Nachbarteil mit der grössten Kontaktfläche.

    Verhindert Restteile von wenigen Kubikmillimetern (z.B. ein Geschoss, von dem nach dem
    Zuordnen fast nichts übrig blieb). Mit ``count`` nur die Labels 0 … count−1 (Geschosse): Dächer und
    Deckel bleiben eigene Teile, auch wenn sie klein sind. Rückgabe: Anzahl aufgelöster Teile.
    """
    values, amounts = np.unique(labels[labels >= 0], return_counts=True)
    dissolved = 0
    for value, amount in sorted(zip(values, amounts), key=lambda t: t[1]):
        if amount >= fraction * amounts.sum():
            break
        if count is not None and value >= count:
            continue
        span_slices = find_objects((labels == value).astype(np.int8))[0]
        near = tuple(slice(max(0, s.start - 1), s.stop + 1) for s in span_slices)
        part = labels[near] == value
        neighbors = _other_parts(labels[near][binary_dilation(part) & ~part], value)
        if len(neighbors):
            labels[near][part] = np.bincount(neighbors).argmax()
            dissolved += 1
    return dissolved


def assign_with_message(labels: np.ndarray, names: list[str], storey_count: int, pitch: float) -> list[str]:
    """Stücke nach Auflage und Kleinteile zuordnen und jede Änderung als Warnung melden (keine stillen Fehler)."""
    def mm3(voxel: int) -> str:
        return f"{voxel * pitch ** 3:.0f} mm³"

    warnings = []
    switched, deleted = assign_by_support(labels)
    again, deleted_again = assign_by_support(labels)   # zweite Runde: Stücke, die erst durch die erste eine Auflage bekamen
    switched, deleted = switched + again, deleted + deleted_again
    if switched or deleted:
        text = f"{switched} abgetrennte Stücke dem Teil gegeben, auf dem sie stehen"
        if deleted:
            text += f", lose Splitter ohne Kontakt entfernt ({mm3(deleted)})"
        warnings.append(text + ".")
    previous = set(np.unique(labels[labels >= 0]).tolist())
    assign_small_pieces(labels, storey_count)
    for value in sorted(previous - set(np.unique(labels[labels >= 0]).tolist())):
        warnings.append(f"Teil «{names[value]}» ist kleiner als {SMALL_PART_RATIO:.0%} des Modells "
                         "und wurde an das Nachbarteil angehängt (kein eigenes STL).")
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
