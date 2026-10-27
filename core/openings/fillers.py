"""Füller (Fenster, Türen, Vorhangfassaden) den Wandpaketen zuordnen und ins Gitter setzen.

Zweck:   Aus den Füllern des IFC-Modells entstehen ``Opening``-Objekte im Modellmass (core/openings/windows.py),
         je Wandpaket, in dem der Füller sitzt. ``insert_openings`` wirkt sie auf das fertige Voxelgitter.
Eingabe: IFC-Modell, Massstab, Drehmatrix, skalierte Wandpakete, Mindestmasse, Voxelgrösse, Öffnungsmodi.
Ausgabe: Liste von ``Opening`` (Füller mit unbrauchbarer Geometrie werden übersprungen und gemeldet);
         Anzahl der Öffnungen, die das Gitter verändert haben.
"""

import numpy as np
import trimesh

from core.analysis.ruleset import ScaleParameters
from core.ifc.model import IfcModel
from core.openings import detection, windows
from core.openings.detection import find_hosts, Opening
from core.voxels.elements import PackageScaling
from core.voxels.grid import VoxelGrid


def collect_openings(ifc: IfcModel, scale: int, rot_matrix: np.ndarray, scaled: PackageScaling,
                     min_free: float, pitch_mm: float, warnings: list[str] | None = None) -> list[Opening]:
    """Fenster, Türen und Vorhangfassaden im Modellmass, je Paket, in dem sie sitzen.

    Wirte geometrisch (alle Pakete, in deren Dicke der Füller liegt – Eckfenster haben
    zwei), sonst der IFC-Wirt. Ohne Paket (Loggia-Fenster, Fenster mit Fenster als Wirt)
    entsteht eine freie Öffnung; sie wird nur gesetzt, wenn sie das Gebäude berührt.
    Ein Füller mit unbrauchbarer Geometrie wird übersprungen und in ``warnings`` gemeldet.
    """
    def model(points):
        return None if points is None else trimesh.transform_points(points / scale, rot_matrix)

    result = []
    for f in ifc.filler:
        try:
            result.extend(_openings_per_filler(f, model, scaled, min_free, pitch_mm))
        except (ValueError, IndexError, np.linalg.LinAlgError) as error:
            if warnings is not None:
                warnings.append(f"Öffnung {f.guid} übersprungen: {error}")
    return result


def _openings_per_filler(f, model, scaled: PackageScaling, min_free: float,
                         pitch_mm: float) -> list[Opening]:
    """Öffnungen eines Füllers – je Wandpaket, in dem er sitzt (Eckfenster: zwei)."""
    result = []
    points, opening = model(f.points), model(f.opening)
    parts = [p for p in (points, opening) if p is not None]
    everything = np.concatenate(parts)
    hits = find_hosts(everything, scaled.boxes, 2 * pitch_mm)
    if not hits and (s := scaled.scalings.get(scaled.package_of.get(f.host, -1))) is not None:
        hits = [(s, np.ones(len(everything), dtype=bool))]          # IFC-Wirt, geometrisch nicht gefunden
    n = len(points) if points is not None else 0
    for host, mask in hits or [(None, np.ones(len(everything), dtype=bool))]:
        own = points[mask[:n]] if points is not None and mask[:n].any() else None
        hole = opening[mask[n:]] if opening is not None and mask[n:].any() else None
        if own is None and hole is None:
            continue
        o = detection.opening(f.kind, own, hole, host, min_free, pitch_mm, f.guid)
        if o is not None:
            result.append(o)
    return result


def insert_openings(grid: VoxelGrid, openings: list[Opening], mode_per_variant: dict[str, str],
                    mode_per_guid: dict[str, str], min_wall_mm: float, parameter: ScaleParameters) -> int:
    """Wirkt die Öffnungen auf das Gitter (geschlossen | vertieft | ausgeschnitten, siehe core/openings/windows.py).

    ``mode_per_variant``: Modus je Öffnungsart («windows», «doors»); ``mode_per_guid`` übersteuert einzelne Füller.
    Die Laibung kommt aus den Massstab-Parametern. Rückgabe: Anzahl Öffnungen, die etwas verändert haben.
    """
    return windows.apply(grid, openings, mode_per_variant, min_wall_mm, parameter.reveal_depth_mm,
                         core_mm=parameter.min_core_reveal_mm, mode_per_guid=mode_per_guid)
