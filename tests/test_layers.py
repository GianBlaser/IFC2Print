"""Tests für core/ifc/layers: Materialschichten mehrschichtiger Bauteile."""

from pathlib import Path

import ifcopenshell
import pytest

from core.ifc.layers import layer_thickness_per_guid

# Diese Datei nutzt IfcMaterialLayerSet(Usage); Building-Architecture-IFC2x3.ifc
# dagegen nur einfache IfcMaterial-Zuweisungen (→ leeres dict, siehe Test unten).
TEST_FILE_WITH_LAYERS = Path(__file__).parent.parent / "testdaten" / "ARC_Modell_NEST_230328.ifc"
TEST_FILE_WITHOUT_LAYERS = Path(__file__).parent.parent / "testdaten" / "Building-Architecture-IFC2x3.ifc"


@pytest.fixture(scope="module")
def model():
    return ifcopenshell.open(str(TEST_FILE_WITH_LAYERS))


def test_layer_thickness_dict_structure(model):
    """Keys sind GUIDs, Werte positive reale mm."""
    thicknesses = layer_thickness_per_guid(model)
    assert isinstance(thicknesses, dict)
    for guid, thickness in thicknesses.items():
        assert isinstance(guid, str) and len(guid) == 22  # IFC-GUID-Länge
        assert thickness > 0


def test_layer_thickness_for_multilayer_elements(model):
    """Modell mit IfcMaterialLayerSet → summierte Paketdicken vorhanden."""
    thicknesses = layer_thickness_per_guid(model)
    assert thicknesses, "Erwarte Bauteile mit IfcMaterialLayerSet"


def test_without_layerset_empty_dict():
    """Einfache IfcMaterial-Zuweisung (kein LayerSet) → kein Eintrag."""
    m = ifcopenshell.open(str(TEST_FILE_WITHOUT_LAYERS))
    assert layer_thickness_per_guid(m) == {}
