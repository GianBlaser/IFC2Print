"""Fenster und Türen: Öffnungen auf dem gemeinsamen Voxelgitter.

Fenster, Türen und Vorhangfassaden (core.ifc.openings.Filler) werden nicht selbst
gedruckt. Jede Öffnung wirkt auf das fertige Gitter, über die ganze Dicke des
Wandpakets, in dem sie sitzt (alle Schichten gemeinsam, siehe core/packages/grouping.py):

  geschlossen     Füllkörper einsetzen → die Wand ist voll, auch wenn das Loch schon in
                  der Wandgeometrie steckt. Kein Sturz-Überhang.
  vertieft        voll füllen, dann innen und aussen gleich tief eine flache Laibung ausräumen:
                  mindestens REVEAL_MIN_DEPTH_MM, höchstens die Laibungstiefe des Massstabs, und
                  der Kern dahinter mindestens so dick wie der Mindestkern und die Mindestwand des
                  Druckerprofils (``reveal_depth``). Reicht die Wand dafür nicht, bleibt sie voll.
                  Die Tiefe ist feiner als ein Voxel (VoxelGrid.place_level): 1.2-mm-Wand → je
                  0.2 mm, Kern 0.8 mm; ab 1.5 mm Wand je 0.35 mm.
  ausgeschnitten  Öffnung über die ganze Paketdicke ausschneiden.

Ein Füller kann in mehreren Paketen sitzen (Fenster über Eck: je Schenkel eine
Öffnung). Ohne Paket (Loggia-Fenster zwischen Decke und Stütze, Glasfassade) gilt
die eigene Platte des Füllers, auf die Mindestdicke gebracht – gesetzt wird sie nur,
wenn sie das Gebäude berührt. Alle Masse im Modellmassstab [mm].
Welche Öffnung wo sitzt, bestimmt core/openings/detection.py; diese Datei erzeugt die Körper und wendet sie an.

Erweiterungspunkt: ``fill_body`` erzeugt den eingesetzten Körper. Vordefinierte
Fenstertypen können später hier statt des schlichten Quaders eingesetzt werden.

Eingabe: Öffnungen (``Opening``), Voxelgitter, Modus je Füllerart, Mindestwand und Laibungstiefe [mm]
Ausgabe: verändertes Voxelgitter und Anzahl der Öffnungen, die etwas verändert haben
"""

from collections.abc import Sequence

import numpy as np
import trimesh

from config import OPENING_MIN_WALLS, REVEAL_MIN_DEPTH_MM
from core.analysis.ruleset import ScaleParameters
from core.openings.detection import Opening
from core.voxels.grid import VoxelGrid


OPENING_MODES = ("geschlossen", "ausgeschnitten", "vertieft")


def check_mode(mode: str) -> str:
    """Gibt den Öffnungsmodus zurück; ein unbekannter Modus ist ein Fehler."""
    if mode not in OPENING_MODES:
        raise ValueError(f"Unbekannter Öffnungsmodus «{mode}» – erlaubt: {', '.join(OPENING_MODES)}")
    return mode


# --- Körper -------------------------------------------------------------------------

def box_mesh(axes: np.ndarray, spans: np.ndarray | list) -> trimesh.Trimesh:
    """Quader im Achsensystem ``axes`` mit je (lo, hi) entlang n, u, w."""
    spans = np.asarray(spans, dtype=float)
    pose = np.eye(4)
    pose[:3, :3] = axes.T
    pose[:3, 3] = axes.T @ spans.mean(axis=1)
    return trimesh.creation.box(extents=spans[:, 1] - spans[:, 0], transform=pose)


def fill_body(o: Opening, margin_mm: float) -> trimesh.Trimesh:
    """Körper, der die Öffnung über die ganze Wanddicke schliesst (um ``margin_mm`` grösser
    als Füller und Öffnung, damit keine Fugen-Schlitze bleiben)."""
    return box_mesh(o.axes, [o.thickness, *(o.filling + [-margin_mm, margin_mm])])


def cutout(o: Opening, pitch_mm: float) -> trimesh.Trimesh:
    lo, hi = o.thickness
    return box_mesh(o.axes, [(lo - pitch_mm, hi + pitch_mm), *o.clear_span])


def reveal_depth(o: Opening, pitch_mm: float, max_mm: float, core_mm: float) -> float:
    """Laibungstiefe je Seite [mm]: höchstens ``max_mm``, der Kern bleibt ≥ ``core_mm``.

    Unter REVEAL_MIN_DEPTH_MM: 0, die Öffnung bleibt voll.
    """
    depth = min(max_mm, (o.voxel * pitch_mm - core_mm) / 2)
    return depth if depth >= REVEAL_MIN_DEPTH_MM - 1e-9 else 0.0


def recess(voxel_grid: VoxelGrid, o: Opening, depth_mm: float) -> int:
    """Räumt beidseitig eine Laibung von ``depth_mm`` aus, so gross wie die lichte Öffnung.

    Feld über die ganze Wanddicke: 0.5 im Abstand ``depth_mm`` von der näheren Wandfläche, je Pitch
    tiefer um 1 mehr. Die Wandflächen liegen auf Voxelgrenzen (``o.voxel`` Voxel um die Paketmitte).
    """
    p = voxel_grid.pitch
    middle, half = sum(o.thickness) / 2, o.voxel * p / 2

    def level(centers: np.ndarray) -> np.ndarray:
        inward = half - np.abs(centers @ o.axes[0] - middle)     # Abstand zur näheren Wandfläche
        return 0.5 + (inward - depth_mm) / p

    return voxel_grid.place_level(cutout(o, p), level)


def fill_box(min_xyz: np.ndarray | Sequence[float], max_xyz: np.ndarray | Sequence[float],
             min_wall_mm: float) -> trimesh.Trimesh:
    """Regel «fuellen»: schlichter Quader aus der Bounding Box, dünnste Achse ≥ Mindestwand, mittig."""
    lo, hi = np.asarray(min_xyz, dtype=float), np.asarray(max_xyz, dtype=float)
    dimensions = hi - lo
    thin = int(np.argmin(dimensions))
    dimensions[thin] = max(dimensions[thin], min_wall_mm)
    return trimesh.creation.box(extents=dimensions, transform=trimesh.transformations.translation_matrix((lo + hi) / 2))


# --- Anwenden -----------------------------------------------------------------------

def apply(voxel_grid: VoxelGrid, openings: list[Opening], mode_per_variant: dict[str, str],
             min_wall_mm: float, reveal_mm: float,
             core_mm: float = ScaleParameters.min_core_reveal_mm, mode_per_guid: dict[str, str] | None = None) -> int:
    """Wirkt alle Öffnungen auf das Gitter. Rückgabe: Anzahl Öffnungen, die etwas verändert haben.

    ``mode_per_guid`` übersteuert den Modus einzelner Füller (Ausnahme in der Oberfläche).

    Zu kleine Öffnungen (Breite oder Höhe < 2 × Mindestwand) werden nur gefüllt. Freie
    Öffnungen (ohne Wandpaket) nur, wenn ihr Füllkörper das Gebäude berührt. Der Kern hinter
    einer Laibung ist mindestens ``core_mm`` und die Mindestwand ``min_wall_mm`` dick, die Laibung je Seite
    höchstens ``reveal_mm`` tief.
    """
    p = voxel_grid.pitch
    changed = 0
    for o in openings:
        mode = check_mode((mode_per_guid or {}).get(o.guid) or mode_per_variant.get(o.kind, "geschlossen"))
        if o.free and not touches(voxel_grid, o):
            continue
        large_enough = np.all(o.clear_span[:, 1] - o.clear_span[:, 0] >= OPENING_MIN_WALLS * min_wall_mm)
        if mode == "ausgeschnitten" and large_enough:
            n = voxel_grid.place(cutout(o, p), False)
        else:
            n = voxel_grid.place(fill_body(o, p), True)
            depth = reveal_depth(o, p, reveal_mm, max(core_mm, min_wall_mm))
            if mode == "vertieft" and large_enough and depth:
                n += recess(voxel_grid, o, depth)
        changed += n > 0
    return changed


def touches(voxel_grid: VoxelGrid, o: Opening) -> bool:
    """True, wenn im vergrösserten Füllkörper (Dicke ±1, Fläche ±2 Voxel) schon Gebäude liegt."""
    p = voxel_grid.pitch
    lo, hi = o.thickness
    return voxel_grid.count_inside(box_mesh(o.axes, [(lo - p, hi + p), *(o.filling + [-2 * p, 2 * p])])) > 0
