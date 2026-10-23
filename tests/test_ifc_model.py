"""Tests für core/ifc/model: IFC-Import, Geometrie-Cache und Geschosszuordnung."""

from pathlib import Path

import numpy as np
import pytest

from core.ifc.assignment import room_for
from core.ifc.model import IfcModel
from core.ifc.table import obb_thickness

TEST_DATA = Path(__file__).parent.parent / "testdaten"


@pytest.fixture(scope="module")
def model():
    return IfcModel.open_file(TEST_DATA / "Building-Architecture-IFC2x3.ifc")


def test_open_from_bytes_like_from_file(model):
    from_bytes = IfcModel.from_bytes((TEST_DATA / "Building-Architecture-IFC2x3.ifc").read_bytes())
    assert from_bytes.schema == model.schema == "IFC2X3"
    assert len(from_bytes.building_elements) == len(model.building_elements)


def test_elements_columns_and_bbox(model):
    df = model.building_elements
    assert {"guid", "ifc_class", "predefined_type", "name", "storey", "bbox_x_mm", "thickness_min_mm", "layer_thickness_mm"} <= set(df.columns)
    with_it = df.dropna(subset=["bbox_x_mm"])
    assert len(with_it) > 0
    assert (with_it[["bbox_x_mm", "bbox_y_mm", "bbox_z_mm"]] > 0).all().all()
    # orientierte Box ist nie dicker als die achsparallele
    assert (with_it["thickness_min_mm"] <= with_it[["bbox_x_mm", "bbox_y_mm", "bbox_z_mm"]].min(axis=1) + 1e-6).all()


def test_no_non_physical_elements(model):
    assert not model.building_elements["ifc_class"].isin(["IfcSpace", "IfcOpeningElement"]).any()


def test_geometry_is_computed_only_once(model):
    assert model.geometry is model.geometry
    assert model.building_elements is model.building_elements


def test_obb_thickness_sloped_wall():
    """Eine um 45° gedrehte Wand 4000 × 200 mm: die achsparallele Box ist ~2900 mm, die OBB 200 mm."""
    corners = np.array([[x, y, z] for x in (0, 4000) for y in (0, 200) for z in (0, 2500)], dtype=float)
    c, s = np.cos(np.pi / 4), np.sin(np.pi / 4)
    rotated = corners @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    assert np.ptp(rotated, axis=0)[:2].min() > 2500
    assert obb_thickness(rotated) == pytest.approx(200, rel=1e-3)


def test_storey_via_aggregation():
    """Teile ohne eigenen Container (Plate in CurtainWall o.ä.) erben das Geschoss des Ganzen."""
    import ifcopenshell
    from ifcopenshell.api import aggregate, root, spatial
    f = ifcopenshell.file(schema="IFC4")
    project = root.create_entity(f, ifc_class="IfcProject")
    storey = root.create_entity(f, ifc_class="IfcBuildingStorey", name="OG 1")
    aggregate.assign_object(f, products=[storey], relating_object=project)
    facade = root.create_entity(f, ifc_class="IfcCurtainWall")
    plate = root.create_entity(f, ifc_class="IfcPlate")
    spatial.assign_container(f, products=[facade], relating_structure=storey)
    aggregate.assign_object(f, products=[plate], relating_object=facade)
    assert room_for(facade) == storey
    assert room_for(plate) == storey
    assert room_for(root.create_entity(f, ifc_class="IfcWall")) is None


# --- Einlesen: Familie, Geschossnamen, Versatz (Analysebericht B-01, B-03, B-04, B-09) ---

def _empty_model():
    import ifcopenshell
    from ifcopenshell.api import aggregate, root
    f = ifcopenshell.file(schema="IFC4")
    project = root.create_entity(f, ifc_class="IfcProject")
    return f, project, aggregate, root


def test_family_via_inheritance():
    from core.ifc.assignment import class_family
    assert class_family("IfcSlabStandardCase", "IFC4") == "IfcSlab"
    assert class_family("IfcWallStandardCase", "IFC2X3") == "IfcWall"
    assert class_family("IfcFurniture", "IFC4") == "IfcFurniture"


def test_duplicate_storey_names_become_unique():
    """Zwei Gebäude mit je einem «EG»: ohne Unterscheidung verschmolzen sie und ein Teil ging verloren."""
    from core.parts.storey_joints import storey_heights
    from core.ifc.assignment import room_names
    f, project, aggregate, root = _empty_model()
    site = root.create_entity(f, ifc_class="IfcSite", name="Grundstück")
    aggregate.assign_object(f, products=[site], relating_object=project)
    storeys = []
    for house in ("Haus A", "Haus B"):
        building = root.create_entity(f, ifc_class="IfcBuilding", name=house)
        aggregate.assign_object(f, products=[building], relating_object=site)
        ground_floor = root.create_entity(f, ifc_class="IfcBuildingStorey", name="EG")
        aggregate.assign_object(f, products=[ground_floor], relating_object=building)
        storeys.append(ground_floor)
    names = room_names(f)
    assert {names[g.id()] for g in storeys} == {"EG (Haus A)", "EG (Haus B)"}
    assert names[site.id()] == "Grundstück"
    same = root.create_entity(f, ifc_class="IfcBuildingStorey", name="EG")      # ohne Gebäude
    assert len(set(room_names(f).values())) == len(room_names(f))
    assert room_names(f)[same.id()].startswith("EG")
    from ifcopenshell.api import geometry
    for g in storeys:
        geometry.edit_object_placement(f, product=g)            # Fugenhöhe kommt aus der Placement
    heights = storey_heights(f, 200)
    assert sorted(n for n, _ in heights) == ["EG (Haus A)", "EG (Haus B)"]


def test_table_elements_only(model):
    """Annotationen, Raster und das Grundstück selbst sind keine Bauteile (früher «ohne Geometrie»)."""
    import ifcopenshell
    ifc_classes = set(model.building_elements["ifc_class"])
    assert all(model.model.by_guid(g).is_a("IfcElement") for g in model.building_elements["guid"])
    assert not ifc_classes & {"IfcSite", "IfcAnnotation", "IfcGrid", "IfcOpeningElement", "IfcSpace"}
    assert {"class_family", "aggregate", "mesh_defective"} <= set(model.building_elements.columns)


def test_parts_of_a_roof_know_their_aggregate(model):
    df = model.building_elements
    assert (df.loc[df["aggregate"] != "", "aggregate"] == "IfcRoof").all()
    assert (df["aggregate"] == "IfcRoof").sum() == 2


def _georeferenced(dx: float, dy: float):
    """Building-Architecture mit verschobenem Grundstück (Modelleinheit mm) – wie ein LV95-Modell."""
    import ifcopenshell
    f = ifcopenshell.open(str(TEST_DATA / "Building-Architecture-IFC2x3.ifc"))
    location = f.by_type("IfcSite")[0].ObjectPlacement.RelativePlacement.Location
    x, y, z = location.Coordinates
    location.Coordinates = (x + dx, y + dy, z)
    return IfcModel(f)


def test_offset_with_national_coordinates(model):
    """LV95 (x ≈ 2 600 000 m): Geometrie wird im Grundriss zum Ursprung verschoben, Höhe bleibt."""
    geo = _georeferenced(2_600_000_000.0, 1_200_000_000.0)
    assert geo.offset_mm[0] > 2.5e9 and geo.offset_mm[1] > 1.1e9 and geo.offset_mm[2] == 0
    lo, hi = geo.extent_mm()
    assert np.abs(lo[:2]).max() < 1e6
    lo0, hi0 = model.extent_mm()
    assert hi - lo == pytest.approx(hi0 - lo0, abs=1e-3)
    assert lo[2] == pytest.approx(lo0[2], abs=1e-3)
    assert len(geo.filler) == len(model.filler)
    assert model.offset_mm.tolist() == [0.0, 0.0, 0.0]                 # lokale Modelle unverändert
