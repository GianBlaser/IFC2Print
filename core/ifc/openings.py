"""IFC-Öffnungen: Fenster, Türen, Vorhangfassaden (Füller) und Öffnungen ohne Füller.

Wirt und Öffnung kommen über IfcRelFillsElement (Öffnung ← Füller) und IfcRelVoidsElement
(Wirt ← Öffnung). Fehlen diese Beziehungen, sucht die Pipeline den Wirt geometrisch.
  * ``find_fillers``: Füller mit eigener Geometrie, Öffnungskörper und Wirt (falls im IFC).
  * ``find_voids``: Öffnungen ohne Fenster oder Tür (Treppenaugen, Schächte, Durchgänge) je Wirt-GUID.

Eingabe: IFC-Modell und die triangulierte Geometrie (``core/ifc/geometry``)
Ausgabe: Liste von ``Filler`` bzw. Öffnungsgeometrie je Wirt-GUID (reale mm, Welt)
"""

from collections.abc import Callable
from dataclasses import dataclass

import ifcopenshell
import ifcopenshell.util.element
import numpy as np

from core.ifc.geometry import Geometry

# Bauteile, die eine Wandöffnung füllen, und ihre Art (steuert Fenster- bzw. Türmodus)
FILLER_CLASSES = {"IfcWindow": "windows", "IfcDoor": "doors", "IfcCurtainWall": "windows"}


@dataclass(frozen=True)
class Filler:
    """Fenster, Tür oder Vorhangfassade (reale mm, Welt). Punkte/Öffnung fehlen, wenn nicht im IFC."""
    guid: str
    ifc_class: str                       # IfcWindow | IfcDoor | IfcCurtainWall
    kind: str                          # windows | doors (Schlüssel des Öffnungsmodus)
    points: np.ndarray | None         # eigene Geometrie (bzw. die seiner Teile)
    opening: np.ndarray | None       # Punkte des IfcOpeningElement (Rohbaumass)
    host: str | None                  # GUID des Bauteils, in dem die Öffnung sitzt


def find_fillers(model: ifcopenshell.file, raw: dict[str, Geometry], geometry: dict[str, Geometry],
                 triangulate_missing: Callable[[list], dict[str, Geometry]]) -> list[Filler]:
    """Fenster, Türen und Vorhangfassaden mit Öffnungskörper und Wirt-Bauteil (falls im IFC).

    ``raw``: alle triangulierten Elemente samt Aussparungen, ``geometry``: nur die Bauteile.
    ``triangulate_missing``: trianguliert Öffnungen nach, die nicht in ``raw`` stehen.
    Hat ein Füller keine eigene Geometrie (Vorhangfassade aus Platten/Pfosten), zählen die Punkte seiner Teile.
    """
    opening_of = {rel.RelatedBuildingElement.GlobalId: rel.RelatingOpeningElement
                    for rel in model.by_type("IfcRelFillsElement")}
    host_of = {rel.RelatedOpeningElement.GlobalId: rel.RelatingBuildingElement.GlobalId
                for rel in model.by_type("IfcRelVoidsElement")}
    # Aussparungen kommen aus dem ersten Lauf; nur fehlende werden nachtrianguliert
    missing_items = [o for o in opening_of.values() if o.GlobalId not in raw]
    opening_geo = {**raw, **(triangulate_missing(missing_items) if missing_items else {})}
    result = []
    for ifc_class, kind in FILLER_CLASSES.items():
        for element in model.by_type(ifc_class):
            points = _points(element, geometry)
            opening = opening_of.get(element.GlobalId)
            geo = opening_geo.get(opening.GlobalId) if opening is not None else None
            if points is None and geo is None:
                continue
            result.append(Filler(
                guid=element.GlobalId, ifc_class=ifc_class, kind=kind, points=points,
                opening=geo.verts if geo is not None else None,
                host=host_of.get(opening.GlobalId) if opening is not None else None))
    return result


def find_voids(model: ifcopenshell.file, raw: dict[str, Geometry], fillers: list[Filler]) -> dict[str, list[Geometry]]:
    """Öffnungen ohne Fenster oder Tür (Treppenaugen, Schächte, Durchgänge) je Wirt-GUID (reale mm, Welt).

    Die Triangulierung zieht Öffnungen nicht ab; die Pipeline schneidet diese hier im Voxelgitter
    aus ihrem Wirt aus (core/voxels/shell.py). Öffnungen mit Fenster oder Tür regelt core/openings/windows.py.
    Eine Öffnung, die einen Füller berührt, gehört zu diesem Füller (fehlende IfcRelFillsElement-
    Beziehung) und bleibt ebenfalls core/openings/windows.py überlassen.
    """
    filled = {rel.RelatingOpeningElement.GlobalId for rel in model.by_type("IfcRelFillsElement")}
    filler_boxes = []
    for f in fillers:
        points = f.points if f.points is not None else f.opening
        filler_boxes.append((points.min(axis=0), points.max(axis=0)))
    result: dict[str, list[Geometry]] = {}
    for rel in model.by_type("IfcRelVoidsElement"):
        opening = rel.RelatedOpeningElement
        geo = raw.get(opening.GlobalId)
        if opening.GlobalId in filled or geo is None:
            continue
        lo, hi = geo.verts.min(axis=0), geo.verts.max(axis=0)
        if any((lo < f_hi).all() and (hi > f_lo).all() for f_lo, f_hi in filler_boxes):
            continue
        result.setdefault(rel.RelatingBuildingElement.GlobalId, []).append(geo)
    return result


def _points(element, geometry: dict[str, Geometry]) -> np.ndarray | None:
    """Punkte eines Bauteils oder – ohne eigene Geometrie – seiner Teile (reale mm)."""
    if (geo := geometry.get(element.GlobalId)) is not None:
        return geo.verts
    parts = [geometry[t.GlobalId].verts for t in ifcopenshell.util.element.get_decomposition(element)
             if t.GlobalId in geometry]
    return np.concatenate(parts) if parts else None
