"""Materialschichten mehrschichtiger Bauteile.

Eingabe: IFC-Modell (ifcopenshell)
Ausgabe: Gesamtdicke der Materialschichten je GUID (mm)

Liest die konstruktive Gesamtdicke aus dem IfcMaterialLayerSet eines Bauteils.
Hintergrund: Mehrschichtige Bauteile (Wände, Decken, Dächer, Fassaden) tragen in
IFC eine Materialschichtung. Für die Druckbarkeitsprüfung ist die Summe aller
Schichtdicken (= das ganze Bauteilpaket) aussagekräftiger als die kleinste
Bounding-Box-Kante, die eine einzelne dünne Schicht widerspiegeln kann.
"""

import ifcopenshell.util.element
import ifcopenshell.util.unit


def _layerset(material) -> object | None:
    """Gibt das IfcMaterialLayerSet eines get_material()-Ergebnisses zurück (oder None).

    get_material() liefert je nach Modellierung ein IfcMaterialLayerSetUsage
    (verweist via .ForLayerSet auf das Set), direkt ein IfcMaterialLayerSet oder
    etwas ganz anderes (IfcMaterial, IfcMaterialProfileSet, …). Nur die beiden
    ersten Fälle tragen eine auswertbare Schichtdicke.
    """
    if material is None:
        return None
    if material.is_a("IfcMaterialLayerSetUsage"):
        return material.ForLayerSet
    if material.is_a("IfcMaterialLayerSet"):
        return material
    return None


def layer_thickness_per_guid(model) -> dict[str, float]:
    """Liefert pro GUID die summierte Materialschichtdicke in realen mm (1:1).

    Nur Bauteile mit einem IfcMaterialLayerSet (ggf. über ein LayerSetUsage)
    erscheinen im Ergebnis; alle anderen fehlen (Aufrufer nutzt dann NaN/Fallback).
    IfcOpenShell-Längen sind in Projekteinheiten → unit_scale ×1000 ergibt mm.
    Pro Element gegen fehlende/ungültige Attribute abgesichert, damit ein
    unsauberes Bauteil nicht die ganze Analyse abbricht.
    """
    scale = ifcopenshell.util.unit.calculate_unit_scale(model)  # Faktor → Meter
    result: dict[str, float] = {}
    for element in model.by_type("IfcProduct"):
        guid = getattr(element, "GlobalId", None)
        if not guid:
            continue
        try:
            material = ifcopenshell.util.element.get_material(element)
            layerset = _layerset(material)
            if layerset is None:
                continue
            sum_m = sum(
                float(layer.LayerThickness)
                for layer in (layerset.MaterialLayers or [])
                if layer.LayerThickness is not None
            )
            thickness_mm = sum_m * scale * 1000
            if thickness_mm > 0:
                result[guid] = thickness_mm
        except (AttributeError, TypeError, ValueError):
            continue
    return result
