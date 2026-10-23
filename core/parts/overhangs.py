"""Überhänge je Druckteil: Wo braucht ein Teil Stützen, wo genügt eine Brücke?

Zweck:   Prüft jedes Teil so, wie es gedruckt wird (unterste Schicht auf dem Bett). Ein Voxel ist getragen, wenn in
         der Schicht darunter er selbst oder ein Nachbar zum selben Teil gehört (45°-Regel bei würfelförmigen Voxeln).
         Ein ungetragener Voxel liegt auf einer Brücke, wenn getragenes Material derselben Schicht höchstens
         ``BRIDGE_MAX_MM`` / 2 entfernt ist (die Brücke liegt beidseitig auf); sonst braucht die Stelle Stützen.
         Stützen stehen auf dem Bett, wenn unter der Stelle nichts vom Teil liegt, sonst auf dem Modell
         (z.B. unter einer Decke über Räumen – dort lassen sie sich kaum entfernen).
Eingabe: Label-Gitter der Aufteilung (core/parts/partitioning.py), Teilnamen, Voxelgrösse und Ursprung des Gitters
Ausgabe: ``Overhang`` je Teil (Flächen, grösste Stützstelle) und ein rotes Markierungsnetz für den Viewer
"""

from dataclasses import dataclass

import numpy as np
import trimesh
from scipy.ndimage import distance_transform_edt, find_objects, label

from config import BRIDGE_MAX_MM, OVERHANG_MIN_MM2, OVERHANG_ON_MODEL_RATIO, VIEWER_MAX_FACES

_MAX_BOXES = VIEWER_MAX_FACES // 4 // 12                       # Markierung: höchstens ¼ des Viewer-Budgets


@dataclass
class Overhang:
    """Überhänge eines Teils; Flächen in Modell-mm²."""
    name: str
    support_mm2: float                       # braucht Stützen
    bridge_mm2: float                        # als Brücke druckbar
    on_model_mm2: float                      # Teil der Stützfläche, unter dem das Teil selbst liegt
    largest: tuple[float, float, float]      # grösste Stützstelle: Länge, Breite, Höhe über dem Bett (mm)
    center: np.ndarray                       # Punkt der grössten Stützstelle nahe ihrer Mitte (Modell-mm)
    voxels: np.ndarray                       # Gitter-Indizes (n × 3) der Stützvoxel – für die Markierung

    @property
    def relevant(self) -> bool:
        return self.support_mm2 >= OVERHANG_MIN_MM2


def overhangs(labels: np.ndarray, names: dict[int, str], pitch: float, origin: np.ndarray) -> list[Overhang]:
    """Überhänge je Teil (``names``: Label → Teilname, wie ``Partition.mesh_names``), Teile ohne Stützbedarf inklusive."""
    boxes = find_objects(labels + 1)                            # Index w ↔ Label w (Werte sind um 1 verschoben)
    radius = BRIDGE_MAX_MM / 2 / pitch                          # Brücke: Abstand zum Auflager in Voxeln
    result = []
    for value, name in names.items():
        if value >= len(boxes) or boxes[value] is None:
            continue
        box = boxes[value]
        support, bridge, on_model = _loose_voxels(labels[box] == value, radius)
        if len(support):
            support = support + [s.start for s in box]
        largest, center = _largest(support, pitch, origin, box[2].start)
        result.append(Overhang(name, len(support) * pitch ** 2, bridge * pitch ** 2, on_model * pitch ** 2,
                               largest, center, support))
    return result


def _loose_voxels(part: np.ndarray, radius: float) -> tuple[np.ndarray, int, int]:
    """Schicht für Schicht (wenig Speicher): (Stützvoxel als lokale Indizes, Anzahl Brückenvoxel, davon auf dem Modell)."""
    support, bridge, on_model = [], 0, 0
    below = np.zeros(part.shape[:2], dtype=bool)               # irgendwo darunter liegt das Teil
    for k in range(1, part.shape[2]):
        below |= part[:, :, k - 1]
        loose = part[:, :, k] & ~_with_neighbours(part[:, :, k - 1])
        if not loose.any():
            continue
        held = part[:, :, k] & ~loose
        far = loose.copy()
        if held.any():                                          # nur um die ungetragenen Voxel rechnen
            i, j = np.nonzero(loose)
            r = int(np.ceil(radius)) + 1
            window = (slice(max(0, i.min() - r), i.max() + r + 1), slice(max(0, j.min() - r), j.max() + r + 1))
            far[window] &= distance_transform_edt(~held[window]) > radius
        bridge += int((loose & ~far).sum())
        on_model += int((far & below).sum())
        i, j = np.nonzero(far)
        support.append(np.column_stack([i, j, np.full(len(i), k)]))
    support = np.concatenate(support) if support else np.zeros((0, 3), dtype=np.int64)
    return support, bridge, on_model


def _with_neighbours(layer: np.ndarray) -> np.ndarray:
    """Schicht samt den 8 Nachbarn jedes Voxels (45°-Regel); zwei Verschiebungen statt binary_dilation – 10× schneller."""
    rows = layer.copy()
    rows[1:] |= layer[:-1]
    rows[:-1] |= layer[1:]
    result = rows.copy()
    result[:, 1:] |= rows[:, :-1]
    result[:, :-1] |= rows[:, 1:]
    return result


def _largest(support: np.ndarray, pitch: float, origin: np.ndarray,
             bed: int) -> tuple[tuple[float, float, float], np.ndarray]:
    """Grösste zusammenhängende Stützstelle: (Länge, Breite, Höhe über dem Bett) in mm und ihr Voxel nächst der Mitte.

    Der Voxel statt des Schwerpunkts: Bei einer L-förmigen Stelle läge der Schwerpunkt neben dem Bauteil.
    """
    if not len(support):
        return (0.0, 0.0, 0.0), np.zeros(3)
    lo = support.min(axis=0)
    mask = np.zeros(support.max(axis=0) - lo + 1, dtype=bool)
    mask[tuple((support - lo).T)] = True
    regions, _ = label(mask, structure=np.ones((3, 3, 3), dtype=bool))
    biggest = np.argwhere(regions == np.bincount(regions.ravel())[1:].argmax() + 1) + lo
    extent = (biggest.max(axis=0) - biggest.min(axis=0) + 1) * pitch
    length, width = sorted(extent[:2], reverse=True)
    height = (biggest[:, 2].min() - bed) * pitch
    middle = biggest[np.argmin(((biggest - biggest.mean(axis=0)) ** 2).sum(axis=1))]
    return (float(length), float(width), float(height)), origin + middle * pitch


def message(o: Overhang, element: str | None) -> str:
    """Meldung mit Vorschlag für ein Teil mit Stützbedarf."""
    length, width, height = o.largest
    text = (f"Überhang «{o.name}»: {o.support_mm2 / 100:.1f} cm² brauchen Stützen"
            + (f", davon {o.on_model_mm2 / 100:.1f} cm² über dem Modell" if o.on_model_mm2 >= OVERHANG_MIN_MM2 else "")
            + f"; grösste Stelle {length:.0f} × {width:.0f} mm, {height:.1f} mm über dem Bett"
            + (f" ({element})" if element else "") + ". ")
    if o.on_model_mm2 >= OVERHANG_ON_MODEL_RATIO * o.support_mm2:
        return text + ("Vorschlag: Stützen stünden im Modell und lassen sich kaum entfernen – das Bauteil besser dem "
                       "Teil darüber oder dem Dachteil zuordnen (03 Regeln, Ausnahme je Bauteil).")
    return text + "Vorschlag: Stützen nur vom Druckbett aus genügen (Slicer: «Stützen nur auf dem Druckbett»)."


def summary(items: list[Overhang]) -> str | None:
    """Eine Zeile, wenn kein Teil Stützen braucht (sonst melden die Teile einzeln)."""
    if not items or any(o.relevant for o in items):
        return None
    bridge = sum(o.bridge_mm2 for o in items)
    return ("Überhänge: alle Teile ohne Stützen druckbar" +
            (f" ({bridge / 100:.1f} cm² als Brücken bis {BRIDGE_MAX_MM:.0f} mm)." if bridge >= OVERHANG_MIN_MM2 else "."))


def mark(o: Overhang, pitch: float, origin: np.ndarray) -> trimesh.Trimesh | None:
    """Rote Markierung: die Stützvoxel als Quader (leicht vergrössert, damit sie aus der Oberfläche ragen).

    Benachbarte Voxel werden zu Rechtecken zusammengefasst (Läufe entlang x, dann gleiche Läufe entlang y),
    sonst hätte eine grosse Deckenfläche Zehntausende Quader.
    """
    if not o.relevant:
        return None
    v = o.voxels[np.lexsort((o.voxels[:, 0], o.voxels[:, 1], o.voxels[:, 2]))]      # nach k, j, i
    start = np.r_[True, (np.diff(v[:, 0]) != 1) | (np.diff(v[:, 1]) != 0) | (np.diff(v[:, 2]) != 0)]
    first = np.flatnonzero(start)
    runs = np.column_stack([v[first, 2], v[first, 1], v[first, 0], v[np.r_[first[1:], len(v)] - 1, 0]])  # k, j, i0, i1
    runs = runs[np.lexsort((runs[:, 1], runs[:, 3], runs[:, 2], runs[:, 0]))]           # nach k, i0, i1, j
    new = np.r_[True, (np.diff(runs[:, [0, 2, 3]], axis=0) != 0).any(axis=1) | (np.diff(runs[:, 1]) != 1)]
    k, i0, i1 = runs[new, 0], runs[new, 2], runs[new, 3]
    j0, j1 = runs[new, 1], np.maximum.reduceat(runs[:, 1], np.flatnonzero(new))
    lo = np.column_stack([i0, j0, k]) - 0.5
    hi = np.column_stack([i1, j1, k]) + 0.5
    if len(lo) > _MAX_BOXES:                                    # nur die grössten Flächen zeigen
        keep = np.argsort((hi - lo)[:, 0] * (hi - lo)[:, 1])[-_MAX_BOXES:]
        lo, hi = lo[keep], hi[keep]
    pad = 0.15                                                  # ragt aus der Oberfläche (in Voxeln)
    return _boxes(origin + (lo - pad) * pitch, origin + (hi + pad) * pitch)


def _boxes(lo: np.ndarray, hi: np.ndarray) -> trimesh.Trimesh:
    """Viele achsparallele Quader als ein Netz (je Fläche eigene Ecken: harte Kanten im Viewer)."""
    unit = trimesh.creation.box(bounds=[[0, 0, 0], [1, 1, 1]])
    corners = unit.vertices[unit.faces].reshape(-1, 3)        # 36 Ecken je Quader
    verts = lo[:, None, :] + corners[None, :, :] * (hi - lo)[:, None, :]
    faces = np.arange(len(lo) * 36).reshape(-1, 3)
    return trimesh.Trimesh(verts.reshape(-1, 3), faces, process=False)
