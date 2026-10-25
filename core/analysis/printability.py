"""Druckbarkeitsprüfung im Modellmassstab.

Eingabe: Bauteiltabelle mit Dicken (real), Massstab, Druckerprofil
Ausgabe: Bauteiltabelle mit Spalte status (druckbar | kritisch | nicht_druckbar)

Status je Bauteil: druckbar | kritisch | nicht_druckbar – vektorisiert über die
ganze Tabelle. Die Bewertungsdicke ist die Dicke des Bauteilpakets (alle direkt
anliegenden Schichten, core/packages/grouping.py), sonst das Materialschichtpaket aus dem IFC,
sonst die kleinste Kante der orientierten Bounding-Box.
"""

import numpy as np
import pandas as pd

from config import (BUILD_VOLUME_X_MM, BUILD_VOLUME_Y_MM, BUILD_VOLUME_Z_MM,
                    CRITICAL_SPAN_MM, MIN_WALL_MM)

PRINTABLE, CRITICAL, NOT_PRINTABLE = "druckbar", "kritisch", "nicht_druckbar"
# Geometrie-Check: unter dieser realen Kantenlänge (mm) gilt ein Mesh als degeneriert
DEGENERATE_MM = 1.0


def status(thickness_model_mm, min_wall_mm: float = MIN_WALL_MM):
    """Status für eine Dicke oder ein Array von Dicken (NaN → nicht_druckbar)."""
    # + 1e-9: 240 mm / 200 = 1.2 soll an der Grenze 0.8 + 0.4 (= 1.2000000000000002) druckbar sein
    d = np.asarray(thickness_model_mm, dtype=float) + 1e-9
    result = np.select(
        [d >= min_wall_mm + CRITICAL_SPAN_MM, d >= min_wall_mm],
        [PRINTABLE, CRITICAL], default=NOT_PRINTABLE)
    return result.item() if result.ndim == 0 else result


def check(df: pd.DataFrame, scale: int, profile: dict | None = None) -> pd.DataFrame:
    """Ergänzt die Bauteiltabelle um thickness_model_mm, status, geometry und fits_in_build_volume.

    ``geometry``: ok | fehlt (kein Mesh) | defekt (flach oder zur Linie/zum Punkt
    kollabiert, kleinste Kante < DEGENERATE_MM real, oder Netz mit nicht endlichen Koordinaten).

    ``profile`` (aus der DB) liefert min_wall_mm und build_volume_*_mm; fehlende
    Werte fallen auf config.py zurück. Gibt eine Kopie zurück.
    """
    profile = profile or {}
    min_wall = profile.get("min_wall_mm", MIN_WALL_MM)
    build_volume = np.array([profile.get("build_volume_x_mm", BUILD_VOLUME_X_MM),
                        profile.get("build_volume_y_mm", BUILD_VOLUME_Y_MM),
                        profile.get("build_volume_z_mm", BUILD_VOLUME_Z_MM)])
    df = df.copy()
    thickness = df["thickness_min_mm"]
    for column_mask in ("layer_thickness_mm", "package_thickness_mm"):      # spätere Spalte hat Vorrang
        if column_mask in df:
            thickness = df[column_mask].fillna(thickness)
    df["thickness_model_mm"] = thickness / scale
    df["status"] = status(df["thickness_model_mm"].to_numpy(), min_wall)
    bbox = df[["bbox_x_mm", "bbox_y_mm", "bbox_z_mm"]].to_numpy(dtype=float)
    mesh_defective = df["mesh_defective"].to_numpy(dtype=bool) if "mesh_defective" in df else np.zeros(len(df), dtype=bool)
    df["geometry"] = np.select([mesh_defective, np.isnan(bbox).any(axis=1), np.nanmin(np.nan_to_num(bbox, nan=np.inf), axis=1) < DEGENERATE_MM],
                                ["defekt", "fehlt", "defekt"], default="ok")
    bbox_model = bbox / scale
    df["fits_in_build_volume"] = ((bbox_model <= build_volume).all(axis=1) |   # gerade oder um 90° gedreht;
                                  (bbox_model[:, [1, 0, 2]] <= build_volume).all(axis=1))   # NaN → False
    return df
