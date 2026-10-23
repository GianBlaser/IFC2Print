"""Einordnung eines IFC-Bauteils: Klassenfamilie, Geschoss (räumlicher Container) und Layer.

  * ``class_family``: erste Klasse aus ``CLASS_FAMILIES`` in der Vererbungskette (IfcSlabStandardCase → IfcSlab).
  * ``room_names`` / ``room_for``: eindeutiger Name und nächster räumlicher Container (Geschoss, Gebäude,
    Grundstück) eines Bauteils.
  * ``layer_per_guid``: Layername(n) aus IfcPresentationLayerAssignment je Bauteil.

Eingabe: IFC-Modell bzw. IFC-Element (ifcopenshell)
Ausgabe: Klassenname, Container oder Name bzw. Layername je GUID
"""

from collections import Counter

import ifcopenshell
import ifcopenshell.util.element

from core.ifc.schema import class_chain

# Klassenfamilien, an denen Sonderlogik hängt (Platten, Gefälle, Dach, Dachträger). Spalte
# «class_family» = erste davon in der Vererbungskette: IfcSlabStandardCase → IfcSlab.
CLASS_FAMILIES = ("IfcWall", "IfcSlab", "IfcRoof", "IfcCovering", "IfcBeam", "IfcColumn", "IfcMember", "IfcPlate",
            "IfcFooting", "IfcStair", "IfcStairFlight", "IfcRailing", "IfcWindow", "IfcDoor", "IfcCurtainWall",
            "IfcBuildingElementPart")


def is_element(element: ifcopenshell.entity_instance) -> bool:
    """Physisches Bauelement – keine Annotation, kein Raster, kein Grundstück, keine Aussparung."""
    return element.is_a("IfcElement") and not element.is_a("IfcFeatureElement")


def class_family(ifc_class: str, schema: str | None) -> str:
    """Erste Klasse aus CLASS_FAMILIES in der Vererbungskette, sonst die Klasse selbst («» bleibt «»)."""
    return next((k for k in class_chain(ifc_class, schema) if k in CLASS_FAMILIES), ifc_class)


def room_names(model: ifcopenshell.file) -> dict[int, str]:
    """Eindeutiger Anzeigename je räumlichem Container (Entity-ID → Name).

    Geschossnamen dienen als Schlüssel für Tabelle, Fugen, Teile und Viewer. Zwei Gebäude
    mit je einem «EG» würden sonst zu einem Geschoss verschmelzen und ein Teil ginge
    verloren. Doppelte Namen erhalten den Namen ihres Gebäudes, notfalls eine Nummer.
    """
    rooms = [r for r in model.by_type("IfcSpatialStructureElement") if not r.is_a("IfcSpace")]
    names = {r.id(): r.Name or "unbekannt" for r in rooms}
    duplicate = {n for n, k in Counter(names.values()).items() if k > 1}
    for r in rooms:
        if names[r.id()] in duplicate and (house := _building(r)) is not None and house is not r and house.Name:
            names[r.id()] = f"{names[r.id()]} ({house.Name})"
    seen: Counter = Counter()
    for r in sorted(rooms, key=lambda r: r.id()):
        seen[names[r.id()]] += 1
        if seen[names[r.id()]] > 1:
            names[r.id()] = f"{names[r.id()]} #{seen[names[r.id()]]}"
    return names


def _building(room):
    """Das IfcBuilding, zu dem ein räumlicher Container gehört (oder None)."""
    while room is not None and not room.is_a("IfcBuilding"):
        room = ifcopenshell.util.element.get_aggregate(room)
    return room


def room_for(element: ifcopenshell.entity_instance) -> ifcopenshell.entity_instance | None:
    """Nächster räumlicher Container (Geschoss, Gebäude, Grundstück) eines Bauteils oder None.

    Klettert über räumliche Zuordnung UND Aggregation nach oben: Teile wie
    IfcStairFlight (in IfcStair) oder IfcPlate (in IfcCurtainWall) haben selbst
    keinen Container, ihr Ganzes schon. Räume (IfcSpace) werden übersprungen.
    """
    while element is not None:
        if element.is_a("IfcSpatialStructureElement") and not element.is_a("IfcSpace"):
            return element
        element = (ifcopenshell.util.element.get_container(element)
                   or ifcopenshell.util.element.get_aggregate(element))
    return None


def layer_per_guid(model: ifcopenshell.file) -> dict[str, str]:
    """Layername(n) je Bauteil-GUID aus IfcPresentationLayerAssignment (mehrere mit « | »).

    Layer hängen an Darstellungen bzw. deren Geometrie-Items; von dort führt der Weg
    über IfcShapeRepresentation → IfcProductDefinitionShape zum Bauteil.
    """
    result: dict[str, set[str]] = {}

    def products_of(item):
        for inv in model.get_inverse(item):
            if inv.is_a("IfcProductDefinitionShape"):
                yield from inv.ShapeOfProduct
            elif inv.is_a("IfcShapeRepresentation"):
                for pds in model.get_inverse(inv):
                    if pds.is_a("IfcProductDefinitionShape"):
                        yield from pds.ShapeOfProduct

    for assignment in model.by_type("IfcPresentationLayerAssignment"):
        for item in assignment.AssignedItems or ():
            for product_entity in products_of(item):
                result.setdefault(product_entity.GlobalId, set()).add(assignment.Name or "")
    return {guid: " | ".join(sorted(names)) for guid, names in result.items()}
