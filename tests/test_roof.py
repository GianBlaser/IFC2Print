"""Tests für core/parts/roof: Stäbe der Dachkonstruktion zählen zum Dachteil."""

from collections import namedtuple
from types import SimpleNamespace

import numpy as np

from core.parts.roof import roof_beam

Row = namedtuple("Row", "guid class_family aggregate storey predefined_type")
ZONES = {"Dach OG": (np.array([0.0, 0.0, 3000.0]), np.array([10000.0, 8000.0, 6000.0]))}   # Dachbox, reale mm


def _model(plates: set[str]) -> SimpleNamespace:
    """Minimales IfcModel: ein Stab je GUID mitten in der Dachbox (Grundriss 5 × 4 m, Höhe 4–4.2 m)."""
    stick = SimpleNamespace(verts=np.array([[1000.0, 3900.0, 4000.0], [9000.0, 4100.0, 4200.0]]))
    return SimpleNamespace(geometry={g: stick for g in ("beam", "member", "roof-stick", "roof-plate", "wall")},
                           plates={g: object() for g in plates}, schema_id="IFC4")


def test_frame_elements_in_the_roof_zone_join_the_roof():
    ifc = _model(plates={"roof-plate"})
    assert roof_beam(ifc, Row("beam", "IfcBeam", "", "OG", ""), ZONES) == "Dach OG"
    assert roof_beam(ifc, Row("member", "IfcMember", "", "OG", ""), ZONES) == "Dach OG"
    # ArchiCAD: Sparren des Dachwerkzeugs als IfcRoof in Balkenform (keine Platte)
    assert roof_beam(ifc, Row("roof-stick", "IfcRoof", "", "OG", ""), ZONES) == "Dach OG"


def test_plates_and_other_classes_are_not_frame_elements():
    ifc = _model(plates={"roof-plate"})
    assert roof_beam(ifc, Row("roof-plate", "IfcRoof", "", "OG", ""), ZONES) is None    # Dachschale: roof_part
    assert roof_beam(ifc, Row("wall", "IfcWall", "", "OG", ""), ZONES) is None


def test_frame_element_outside_the_zone_stays_in_its_storey():
    ifc = _model(plates=set())
    ifc.geometry["member"] = SimpleNamespace(verts=np.array([[20000.0, 0.0, 4000.0], [21000.0, 100.0, 4200.0]]))
    assert roof_beam(ifc, Row("member", "IfcMember", "", "OG", ""), ZONES) is None
