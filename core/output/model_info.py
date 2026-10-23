"""Modell-Info: Kennzahlen des IFC-Modells für die Oberfläche (Abmessungen, Bauraum, Geschosse).

Zweck:   Zeigt, wie gross das Modell im gewählten Massstab wird, ob es aufs Druckbett passt und wie die
         Geschosse (Kote, Höhe, Anzahl Bauteile, Probleme) aussehen.
Eingabe: IFC-Modell, Bauteiltabelle (core.pipeline.analyse), Massstab, Druckerprofil und Ausrichtungswinkel.
Ausgabe: Dictionary mit Abmessungen, Bauraum, Massstab-Empfehlung, Geschossliste und Geometrie-Zählung.
"""

import ifcopenshell.util.unit
import numpy as np
import pandas as pd
import trimesh

from config import BUILD_VOLUME_X_MM, BUILD_VOLUME_Y_MM, BUILD_VOLUME_Z_MM, SCALES
from core.ifc.assignment import room_names
from core.ifc.model import IfcModel
from core.output import preview
from core.output.view_data import storey_order
from core.parts.storey_joints import storey_heights
from core.voxels import alignment


def model_overview(ifc: IfcModel, df: pd.DataFrame, scale: int, profile: dict,
                   angle: float = 0.0) -> dict:
    """Kennzahlen für die Modell-Info im IFC-Modus.

    Abmessungen beziehen sich auf die gedruckten Bauteile (nach der Ausrichtung, wie sie
    aufs Druckbett kommen); gibt es keine, auf alle. Geschosse von unten nach oben mit
    Kote (IfcBuildingStorey.Elevation, Architekten-±0.00) und Höhe (Abstand zur nächsten
    Geschoss-Z im Weltsystem; beim obersten bis zur Oberkante seiner Bauteile).
    """
    build_volume = [profile.get("build_volume_x_mm", BUILD_VOLUME_X_MM), profile.get("build_volume_y_mm", BUILD_VOLUME_Y_MM),
                    profile.get("build_volume_z_mm", BUILD_VOLUME_Z_MM)]
    result: dict = {"scale": scale, "dimensions_m": None, "bauraum_mm": build_volume}
    result.update(_dimensions(ifc, df, scale, build_volume, angle))
    result["storeys"] = _storey_summary(ifc, df)
    result["geometry"] = {k: int((df["geometry"] == k).sum()) for k in ("ok", "fehlt", "defekt")}
    return result


def _dimensions(ifc: IfcModel, df: pd.DataFrame, scale: int, build_volume: list[float], angle: float) -> dict:
    """Abmessungen in m (real) und mm (Modell), ob das Modell aufs Bett passt, und die Massstab-Empfehlung."""
    rot_matrix = alignment.model_rotation(ifc, 1, angle)
    guids = [g for g in df.loc[df["is_printed"], "guid"] if g in ifc.geometry] or \
            [g for g in df["guid"] if g in ifc.geometry]
    if not guids:
        return {}
    points = trimesh.transform_points(np.concatenate([ifc.geometry[g].verts for g in guids]), rot_matrix)
    real_m = np.ptp(points, axis=0) / 1000
    model_mm = real_m * 1000 / scale
    factor = float(np.max(model_mm / build_volume))
    # Empfehlung: der nächste Massstab, bei dem das Modell aufs Bett passt (None = keine)
    fitting = [z for z in sorted(SCALES.values()) if z >= scale * factor]
    return dict(dimensions_m=real_m.tolist(), model_mm=model_mm.tolist(), fits=factor <= 1.0,
                recommendation=None if factor <= 1.0 or not fitting else fitting[0])


def _storey_summary(ifc: IfcModel, df: pd.DataFrame) -> list[dict]:
    """Geschosse von unten nach oben: Farbe, Kote, Höhe, Anzahl Bauteile und Anzahl Geometrieprobleme."""
    world_z = dict(storey_heights(ifc.model, 1))             # Weltsystem, reale mm
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc.model)
    names = room_names(ifc.model)
    elevations = {names[s.id()]: float(s.Elevation) * unit_scale
                  for s in ifc.model.by_type("IfcBuildingStorey") if s.Elevation is not None}
    order = storey_order(ifc, df)
    floors = [g for g in order if g in world_z]
    storeys = []
    for rank, name in enumerate(order):
        part = df[df["storey"] == name]
        height = _storey_height_m(ifc, part, name, world_z, floors)
        storeys.append({
            "name": name, "color": preview.storey_color(rank),
            "kote_m": elevations.get(name, world_z[name] / 1000 if name in world_z else None),
            "hoehe_m": float(height) if height and height > 0 else None,
            "count": int(len(part)), "problems": int((part["geometry"] != "ok").sum()),
        })
    return storeys


def _storey_height_m(ifc: IfcModel, part: pd.DataFrame, name: str, world_z: dict[str, float],
                     floors: list[str]) -> float | None:
    """Höhe eines Geschosses in m: bis zum nächsten Geschoss, beim obersten bis zur Oberkante seiner Bauteile."""
    if name not in world_z:
        return None
    i = floors.index(name)
    if i + 1 < len(floors):
        return (world_z[floors[i + 1]] - world_z[name]) / 1000
    top = [ifc.geometry[g].verts[:, 2].max() for g in part["guid"] if g in ifc.geometry]
    return (max(top) - world_z[name]) / 1000 if top else None
