"""Misst im erzeugten Voxelgitter die sichtbare Wanddicke je Wandtyp und zählt die Öffnungen.

    python scripts/wall_thicknesses.py testdaten/ARC_Modell_NEST_230328.ifc --scale 1:200 --quality fein

Je gedruckter, achsparalleler Wand wird an 5 Stellen auf halber Höhe die
zusammenhängende Voxelreihe entlang der Wandnormale gezählt. Soll: je Wandtyp eine
einzige Voxelzahl (Kreuzungen und Stösse ergeben einzelne lange Reihen – das ist normal).

Eingabe: IFC-Datei, Massstab (--scale), Qualität (--quality), Öffnungsmodus (--openings)
Ausgabe: Tabelle auf der Konsole – je Wandtyp reale Dicke, Modelldicke und gemessene Voxelzahlen
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # Projektordner importierbar

import numpy as np
import pandas as pd

from config import SCALES, QUALITIES
from core import pipeline
from core.analysis.ruleset import Ruleset
from core.ifc.model import IfcModel
from core.voxels.alignment import model_rotation
from core.voxels.grid import VoxelGrid
from db.database import Database


# Messstellen (Festlegung): Anteile der Wandlänge, ohne die Enden mit den Wandecken
MEASURE_POSITIONS = (0.2, 0.35, 0.5, 0.65, 0.8)
MEASURE_HEIGHT = 0.45            # Messhöhe als Anteil der Wandhöhe
MAX_THICKNESS_TO_LENGTH = 0.5    # Wände, die dicker als die halbe Länge sind (kurz oder schräg), nicht messen

def row_thickness(matrix: np.ndarray, axis: int, idx: np.ndarray) -> int:
    """Länge der zusammenhängenden belegten Reihe durch ``idx`` entlang ``axis`` (0 = leer)."""
    if np.any(idx < 0) or np.any(idx >= matrix.shape) or not matrix[tuple(idx)]:
        return 0
    line_item = matrix[tuple(slice(None) if a == axis else i for a, i in enumerate(idx))]
    i = idx[axis]
    empty = np.flatnonzero(~line_item)
    return int((empty[empty > i].min() if (empty > i).any() else len(line_item))
               - (empty[empty < i].max() if (empty < i).any() else -1) - 1)


def read_arguments() -> argparse.Namespace:
    """Liest die Kommandozeile (IFC-Datei, Massstab, Qualität, Öffnungsmodus)."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ifc", type=Path)
    p.add_argument("--scale", choices=list(SCALES), default="1:200")
    p.add_argument("--quality", choices=list(QUALITIES), default="fein")
    p.add_argument("--openings", default="vertieft", help="geschlossen | vertieft | ausgeschnitten")
    return p.parse_args()


def measure_walls(ifc: IfcModel, df: pd.DataFrame, voxel_grid: VoxelGrid, scale: int, pitch: float,
                  rot_matrix: np.ndarray) -> tuple[dict, dict]:
    """Zählt je Wandtyp an 5 Stellen die Voxelreihe; Rückgabe (Verteilung der Voxelzahlen, reale Dicke) je Wandtyp."""
    per_type_code, real = defaultdict(Counter), {}
    for z in df[df["is_printed"] & df["ifc_class"].str.startswith("IfcWall")].itertuples():
        if z.guid not in ifc.geometry:
            continue
        lo, hi = ifc.geometry[z.guid].mesh(scale, rot_matrix).bounds
        extent = hi - lo
        axis = int(np.argmin(extent[:2]))
        if extent[axis] > MAX_THICKNESS_TO_LENGTH * extent[1 - axis]:      # zu kurz oder schräg: nicht messbar
            continue
        type_name = z.name.split(":")[1] if z.name.count(":") >= 2 else z.name
        real[type_name] = z.thickness_min_mm
        for f in MEASURE_POSITIONS:
            point = lo + extent / 2
            point[1 - axis] = lo[1 - axis] + extent[1 - axis] * f
            point[2] = lo[2] + extent[2] * MEASURE_HEIGHT
            if n := row_thickness(voxel_grid.matrix, axis, np.rint((point - voxel_grid.origin) / pitch).astype(int)):
                per_type_code[type_name][n] += 1
    return per_type_code, real


def print_table(per_type_code: dict, real: dict, scale: int, pitch: float) -> None:
    """Gibt je Wandtyp die reale Dicke, die Modelldicke und die gemessenen Voxelzahlen aus."""
    print(f"\n{'Wandtyp':50s} {'real':>6s} {'Modell':>7s}  gemessen (Voxel = mm × Anzahl Stellen)")
    for predefined_type in sorted(per_type_code, key=real.get):
        distribution = "  ".join(f"{n}={n * pitch:.1f}×{k}" for n, k in sorted(per_type_code[predefined_type].items()))
        print(f"{predefined_type[:50]:50s} {real[predefined_type]:6.0f} {real[predefined_type] / scale:7.2f}  {distribution}")


def main() -> None:
    args = read_arguments()
    db = Database()
    profile, material = db.profiles()[0], db.materials()[0]
    scale, pitch = SCALES[args.scale], QUALITIES[args.quality]
    ifc = IfcModel.open_file(args.ifc)
    df = pipeline.analyse(ifc, Ruleset.default(), scale, profile)
    angle = pipeline.alignment_angle(ifc, df)
    res = pipeline.generate(ifc, df, scale=scale, pitch_mm=pitch, profile=profile, material=material,
                            angle=angle, windows=args.openings, doors=args.openings)
    print(f"{args.ifc.name}  1:{scale}  Pitch {pitch} mm  Ausrichtung {angle:.1f}°  "
          f"Öffnungen ({args.openings}): {res.metrics['Öffnungen']} von {len(ifc.filler)} Füllern  "
          f"wasserdicht: {res.watertight}")
    per_type_code, real = measure_walls(ifc, df, res.voxel_grid, scale, pitch, model_rotation(ifc, scale, angle))
    print_table(per_type_code, real, scale, pitch)


if __name__ == "__main__":
    main()
