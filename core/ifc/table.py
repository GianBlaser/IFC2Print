"""Bauteiltabelle: eine Zeile je physischem Bauteil mit Klasse, Geschoss, Layer und Massen.

Eingabe: IFC-Modell, Geometrie-Cache je GUID, GUIDs defekter Netze, Schemakennung
Ausgabe: pandas-DataFrame (Spalten siehe ``element_table``)
"""

import ifcopenshell
import ifcopenshell.util.element
import numpy as np
import pandas as pd
import trimesh

from core.ifc.assignment import class_family, is_element, layer_per_guid, room_for, room_names
from core.ifc.geometry import Geometry
from core.ifc.layers import layer_thickness_per_guid


def element_table(model: ifcopenshell.file, geometry: dict[str, Geometry], defective: set[str], schema_id: str) -> pd.DataFrame:
    """Eine Zeile je physischem Bauteil mit Darstellung (einmalig berechnet, nicht verändern).

    Spalten: guid, ifc_class, class_family (siehe CLASS_FAMILIES), aggregate (Klasse des Aggregats,
    z.B. IfcRoof für seine Platten, sonst «»), predefined_type, name, type_name (Name des Typobjekts),
    layer (IfcPresentationLayerAssignment, z.B. ArchiCAD-Ebene), storey (eindeutiger Name,
    siehe room_names), on_site (direkt im IfcSite statt in einem Geschoss),
    bbox_x/y/z_mm (achsparallel), center_x/y/z_mm (Mitte dieser Box, nach dem Versatz), thickness_min_mm
    (kleinste Kante der *orientierten* Box – stimmt auch für schräge Wände), layer_thickness_mm
    (Materialschichtpaket, falls vorhanden), mesh_defective (nicht endliche Koordinaten).
    Ohne Geometrie: NaN. Nur IfcElement ohne Aussparungen – Annotationen, Raster und das
    Grundstück selbst sind keine Bauteile.
    """
    layer_thickness = layer_thickness_per_guid(model)
    layer = layer_per_guid(model)
    names = room_names(model)
    rows = []
    for element in model.by_type("IfcElement"):
        if not element.Representation or not is_element(element):
            continue
        type_object = ifcopenshell.util.element.get_type(element)
        room = room_for(element)
        aggregate_whole = ifcopenshell.util.element.get_aggregate(element)
        rows.append({
            "guid": element.GlobalId,
            "ifc_class": element.is_a(),
            "class_family": class_family(element.is_a(), schema_id),
            "aggregate": aggregate_whole.is_a() if aggregate_whole is not None and aggregate_whole.is_a("IfcElement") else "",
            "predefined_type": str(getattr(element, "PredefinedType", None) or ""),
            "name": element.Name or "",
            "type_name": (type_object.Name or "") if type_object is not None else "",
            "layer": layer.get(element.GlobalId, ""),
            "storey": names.get(room.id(), "unbekannt") if room is not None else "unbekannt",
            "on_site": room is not None and room.is_a("IfcSite"),
            **_size_columns(geometry.get(element.GlobalId)),
            "layer_thickness_mm": layer_thickness.get(element.GlobalId, np.nan),
            "mesh_defective": element.GlobalId in defective,
        })
    return pd.DataFrame(rows)


def _size_columns(geo: Geometry | None) -> dict[str, float]:
    """Achsparallele Boxgrösse, deren Mitte und kleinste Kante der orientierten Box (NaN ohne Geometrie)."""
    bbox = np.ptp(geo.verts, axis=0) if geo is not None else np.full(3, np.nan)
    center = (geo.verts.min(axis=0) + geo.verts.max(axis=0)) / 2 if geo is not None else np.full(3, np.nan)
    return {
        "bbox_x_mm": bbox[0], "bbox_y_mm": bbox[1], "bbox_z_mm": bbox[2],
        "center_x_mm": center[0], "center_y_mm": center[1], "center_z_mm": center[2],
        "thickness_min_mm": obb_thickness(geo.verts) if geo is not None else np.nan,
    }


def obb_thickness(verts: np.ndarray) -> float:
    """Bauteildicke: kleinste Kante der orientierten oder der achsparallelen Box (reale mm).

    Die orientierte Box erkennt schräge Wände; da sie nach minimalem Volumen sucht,
    kann ihre kleinste Kante aber minim grösser sein als die achsparallele – daher das Minimum.
    """
    axis_parallel = float(np.ptp(verts, axis=0).min())
    if len(verts) < 4:
        return axis_parallel
    try:
        _, extents = trimesh.bounds.oriented_bounds(verts)
    except Exception:  # degenerierte Punktwolke (z.B. alles in einer Ebene)
        return axis_parallel
    return min(float(np.min(extents)), axis_parallel)
