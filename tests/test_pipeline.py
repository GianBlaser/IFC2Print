"""End-to-End-Tests der Orchestrierung (core/pipeline) gegen echte IFC-Testmodelle."""

from pathlib import Path

import pytest

from config import QUALITIES
from core import pipeline
from core.analysis.ruleset import Ruleset
from core.ifc.model import IfcModel
from core.output import report

TEST_DATA = Path(__file__).parent.parent / "testdaten"
PROFILE = {"name": "Test", "min_wall_mm": 0.8, "layer_height_mm": 0.2,
          "build_volume_x_mm": 250.0, "build_volume_y_mm": 210.0, "build_volume_z_mm": 220.0}
MATERIAL = {"name": "PLA", "density_g_cm3": 1.24, "price_chf_kg": 25.0}


@pytest.fixture(scope="module")
def mfh():
    ifc = IfcModel.open_file(TEST_DATA / "MFH_eBKPH_Test.ifc")
    return ifc, pipeline.analyse(ifc, Ruleset.default(), 200, PROFILE)


@pytest.fixture(scope="module")
def result(mfh):
    ifc, df = mfh
    return pipeline.generate(ifc, df, scale=200, pitch_mm=QUALITIES["entwurf"], profile=PROFILE, material=MATERIAL)


def test_analysis_columns_and_rules(mfh):
    _, df = mfh
    assert {"action", "is_printed", "category", "status", "thickness_model_mm", "fits_in_build_volume"} <= set(df.columns)
    assert df.loc[df["ifc_class"] == "IfcWall", "is_printed"].all()
    facade = df[(df["ifc_class"] == "IfcCovering") & (df["predefined_type"] == "CLADDING")]
    assert len(facade) and facade["is_printed"].all()                    # spezifische Regel gewinnt
    assert not df.loc[(df["ifc_class"] == "IfcCovering") & (df["predefined_type"] != "CLADDING"), "is_printed"].any()


def test_storeys_from_bottom_to_top(mfh):
    ifc, df = mfh
    order = pipeline.storey_order(ifc, df)
    assert order.index("UG") < order.index("EG") < order.index("Dach")


def test_generate_watertight_per_storey(result):
    assert result.watertight
    assert list(result.parts) == ["UG", "EG", "1. OG", "2. OG", "Dach"]
    assert result.grams > 0 and result.cost_chf > 0 and result.time_h > 0


def test_volume_matches_voxels(result):
    """Regression: Hüllvolumen ≈ Voxelvolumen (früher zählten eingeschlossene Räume mit, ×6.5)."""
    g = result.voxel_grid
    voxel_cm3 = g.matrix.sum() * g.pitch ** 3 / 1000
    assert result.volume_cm3 == pytest.approx(voxel_cm3, rel=0.05)


def test_downloads(result, mfh):
    _, df = mfh
    assert len(result.combined.faces) == sum(len(m.faces) for m in result.parts.values())
    assert len(result.stl()) > 84
    assert result.stl_zip("mfh")[:2] == b"PK"
    assert len(result.stl_plate(PROFILE)) > 84
    assert b"klasse" in pipeline.elements_csv(df)               # Kopfzeile deutsch (CSV_HEADERS)
    assert all(glb[:4] == b"glTF" for glb in result.preview.values())


def test_result_carries_what_the_report_needs(result):
    """Prüfpunkte des Laufs strukturiert, die Warnungen als Sätze wie bisher; Überhänge und Einstellungen."""
    cut = next(p for p in result.check_points if p["kind"] == "oeffnungen")
    n = sum(count for _, count in cut["entries"])
    assert f"{n} Öffnungen ohne Fenster oder Tür ausgeschnitten (Treppenaugen, Schächte, Durchgänge)." in result.warnings
    assert not any(p["category"] == "georeferenz" and p["kind"] != "versatz" for p in result.check_points)
    assert {o.name for o in result.overhangs} <= set(result.parts)
    assert result.settings["scale"] == 200 and result.settings["profile"]["name"] == "Test"
    assert (result.connector_count, result.pegs_per_part) == (0, {})


@pytest.mark.skipif(not report.available(), reason="WeasyPrint/Pango fehlt")
def test_report_pdf(result, mfh):
    ifc, df = mfh
    context = pipeline.report_context(ifc, df, "MFH_eBKPH_Test.ifc", scale=200, ruleset_name="1:200",
                                      profile=PROFILE, material=MATERIAL)
    assert result.report_pdf(df, context)[:4] == b"%PDF"


def test_preview_per_storey(mfh):
    ifc, df = mfh
    status = pipeline.status_preview(ifc, df, 200)
    assert list(status) == pipeline.storey_order(ifc, df)
    assert all(glb[:4] == b"glTF" for glb in status.values())
    ifc_glb = pipeline.ifc_preview(ifc, df, 200)
    assert set(ifc_glb) == set(status)
    assert all(normal is None or normal[:4] == b"glTF" for normal, _ in ifc_glb.values())


def test_status_preview_colors_only_printed(mfh):
    ifc, df = mfh
    everything = pipeline.status_preview(ifc, df, 200)
    nothing = pipeline.status_preview(ifc, df.assign(is_printed=False), 200)
    assert b"ausgeschlossen" in b"".join(nothing.values())
    assert b"ausgeschlossen" not in b"".join(everything.values()) or not df["is_printed"].all()
    assert b"druckbar" not in b"".join(nothing.values())


def test_model_overview(mfh):
    ifc, df = mfh
    u = pipeline.model_overview(ifc, df, 200, PROFILE)
    assert len(u["dimensions_m"]) == 3 and all(v > 0 for v in u["dimensions_m"])
    assert u["fits"] is True and u["recommendation"] is None
    floors = [g for g in u["storeys"] if g["hoehe_m"]]
    assert [g["name"] for g in floors][:2] == ["UG", "EG"]
    assert all(g["hoehe_m"] == pytest.approx(3.0) for g in floors[:-1])   # Dach ist niedriger
    assert sum(u["geometry"].values()) == len(df)
    assert len({g["color"] for g in u["storeys"]}) == len(u["storeys"])
    large = pipeline.model_overview(ifc, df, 50, PROFILE)        # 1:50 ist zu gross fürs Bett
    assert large["fits"] is False and large["recommendation"] > 50


def test_thicken_and_fill_take_effect(mfh):
    """Mit «verdicken» für alle Wände und «fuellen» für Treppen wächst das Volumen; Kennzahlen zählen es."""
    ifc, _ = mfh
    rules = {**Ruleset.default().rules, "IfcCovering": "verdicken", "IfcStair": "fuellen"}
    df = pipeline.analyse(ifc, Ruleset(rules), 200, PROFILE)
    basis = pipeline.analyse(ifc, Ruleset.default(), 200, PROFILE)
    kw = dict(scale=200, pitch_mm=QUALITIES["entwurf"], profile=PROFILE, material=MATERIAL)
    with_it, without_it = pipeline.generate(ifc, df, **kw), pipeline.generate(ifc, basis, **kw)
    assert with_it.metrics["Verdickt"] > 0 and with_it.metrics["Gefüllt"] > 0
    assert with_it.volume_cm3 > without_it.volume_cm3


def test_keep_prints_unchanged(mfh):
    """«behalten» dickt ein zu dünnes Einzelbauteil nicht auf, «verdicken» schon."""
    ifc, df = mfh
    single = df.index[df["is_printed"] & (df["package"] < 0) & ~df["action"].isin(["fuellen", "band"])][0]
    kw = dict(scale=200, pitch_mm=QUALITIES["entwurf"], profile=PROFILE, material=MATERIAL)
    thickened = {}
    for action in ("behalten", "verdicken"):
        thin = df.copy()
        thin.loc[single, ["action", "thickness_model_mm"]] = [action, 0.3]       # dünner als die Mindestwand 0.8 mm
        thickened[action] = pipeline.generate(ifc, thin, **kw).metrics["Verdickt"]
    assert thickened["verdicken"] == thickened["behalten"] + 1


def test_opening_modes(mfh):
    """Ausgeschnitten nimmt am meisten weg, vertieft weniger, geschlossen nichts – alles bleibt dicht."""
    ifc, df = mfh
    kw = dict(scale=200, pitch_mm=QUALITIES["entwurf"], profile=PROFILE, material=MATERIAL)
    vol = {m: pipeline.generate(ifc, df, windows=m, doors=m, **kw)
           for m in ("geschlossen", "vertieft", "ausgeschnitten")}
    assert all(e.watertight for e in vol.values())
    assert vol["geschlossen"].volume_cm3 > vol["vertieft"].volume_cm3 > vol["ausgeschnitten"].volume_cm3
    assert vol["vertieft"].metrics["Fenster"] == "vertieft"


def test_alignment_rotated_building(mfh, tmp_path):
    """Ein um 23° gedrehtes MFH wird erkannt, zurückgedreht und hat danach so wenige Stufen wie das Original."""
    import math
    import ifcopenshell
    file = ifcopenshell.open(str(TEST_DATA / "MFH_eBKPH_Test.ifc"))
    site_placement = file.by_type("IfcSite")[0].ObjectPlacement.RelativePlacement
    site_placement.RefDirection = file.createIfcDirection((math.cos(math.radians(23)), math.sin(math.radians(23)), 0.0))
    if site_placement.Axis is None:
        site_placement.Axis = file.createIfcDirection((0.0, 0.0, 1.0))
    file.write(str(tmp_path / "gedreht.ifc"))

    rotated = IfcModel.open_file(tmp_path / "gedreht.ifc")
    df = pipeline.analyse(rotated, Ruleset.default(), 200, PROFILE)
    angle = pipeline.alignment_angle(rotated, df)
    assert angle == pytest.approx(23.0, abs=0.1)
    assert pipeline.alignment_angle(*mfh) == 0.0

    kw = dict(scale=200, pitch_mm=QUALITIES["entwurf"], profile=PROFILE, material=MATERIAL)
    triangles = lambda e: sum(len(m.faces) for m in e.parts.values())
    skewed, straight = pipeline.generate(rotated, df, **kw), pipeline.generate(rotated, df, angle=angle, **kw)
    assert triangles(straight) < 0.9 * triangles(skewed)
    assert straight.metrics["Ausrichtung (°)"] == "23.0"


def test_no_printable_elements(mfh):
    ifc, _ = mfh
    df = pipeline.analyse(ifc, Ruleset({}), 200, PROFILE)
    with pytest.raises(ValueError):
        pipeline.generate(ifc, df, scale=200, pitch_mm=0.8, profile=PROFILE, material=MATERIAL)


def test_filename():
    assert pipeline.filename("1. OG / Nord") == "1._OG_Nord"
    assert pipeline.filename("///") == "teil"


def test_element_at_point_picks_smallest_box():
    import numpy as np
    import pandas as pd
    df = pd.DataFrame({"guid": ["wand", "decke", "weg"], "storey": ["EG"] * 3, "is_printed": [True, True, False]})
    boxes = {"decke": (np.array([0., 0, 0]), np.array([10., 10, 1])),
             "wand": (np.array([0., 0, 0]), np.array([10., 0.8, 10])),
             "weg": (np.array([0., 0, 0]), np.array([0.5, 0.5, 0.5]))}
    assert pipeline.element_at_point(boxes, df, "EG", (5, 0.5, 0.5)) == "wand"      # Wand: kleinere Box
    assert pipeline.element_at_point(boxes, df, "EG", (5, 5, 1.0)) == "decke"
    assert pipeline.element_at_point(boxes, df, "EG", (0.2, 0.2, 0.2), printed_only=False) == "weg"
    assert pipeline.element_at_point(boxes, df, "EG", (50, 50, 50)) is None
    assert pipeline.element_at_point(boxes, df, "OG", (5, 5, 1.0)) is None


def test_selection_preview_and_boxes(mfh):
    ifc, df = mfh
    guid = next(g for g in df["guid"] if g in ifc.geometry)
    glb = pipeline.selection_preview(ifc, df, [guid], 200)
    assert list(glb) == [df.set_index("guid").loc[guid, "storey"]] and glb[next(iter(glb))][:4] == b"glTF"
    lo, hi = pipeline.element_boxes(ifc, 200)[guid]
    center = (lo + hi) / 2
    assert pipeline.element_at_point(pipeline.element_boxes(ifc, 200), df.assign(is_printed=True),
                                     glb and df.set_index("guid").loc[guid, "storey"], center) is not None


# --- Universalität (Analysebericht B-01, B-02, B-12) ------------------------------

def test_export_watertight_detects_float32_problem():
    """In Landeskoordinaten löst float32 nur 1 mm auf: das STL ist nach dem Neuladen nicht mehr dicht."""
    import trimesh
    cube = trimesh.creation.icosphere(subdivisions=3, radius=2.0)
    assert pipeline.export_watertight(cube)
    assert not pipeline.export_watertight(cube.copy().apply_translation([1.3e7, 0, 0]))


def test_lv95_model_stays_watertight_after_export():
    """Building-Architecture auf LV95 verschoben: gleiches Volumen und dichtes STL wie lokal."""
    import ifcopenshell
    def generated(dx):
        f = ifcopenshell.open(str(TEST_DATA / "Building-Architecture-IFC2x3.ifc"))
        location = f.by_type("IfcSite")[0].ObjectPlacement.RelativePlacement.Location
        x, y, z = location.Coordinates
        location.Coordinates = (x + dx, y + dx / 2, z)
        ifc = IfcModel(f)
        df = pipeline.analyse(ifc, Ruleset.default(), 200, PROFILE)
        return pipeline.generate(ifc, df, scale=200, pitch_mm=QUALITIES["entwurf"], profile=PROFILE,
                                 material=MATERIAL)
    local, lv95 = generated(0.0), generated(2_600_000_000.0)
    assert lv95.watertight
    assert lv95.volume_cm3 == pytest.approx(local.volume_cm3, rel=1e-3)
    new = __import__("trimesh").load(__import__("io").BytesIO(lv95.stl()), file_type="stl")
    assert abs(new.bounds).max() < 1e5


def test_standard_case_classes_are_printed(mfh):
    """IFC4-Unterklassen (IfcSlabStandardCase) erben die Regel – früher fehlten alle Decken still."""
    import ifcopenshell
    import ifcopenshell.util.schema
    f = ifcopenshell.open(str(TEST_DATA / "MFH_eBKPH_Test.ifc"))
    for plate in list(f.by_type("IfcSlab")):
        ifcopenshell.util.schema.reassign_class(f, plate, "IfcSlabStandardCase")
    ifc = IfcModel(f)
    df = pipeline.analyse(ifc, Ruleset.default(), 200, PROFILE)
    _, original = mfh
    assert (df["ifc_class"] == "IfcSlabStandardCase").sum() == (original["ifc_class"] == "IfcSlab").sum() > 0
    assert df["is_printed"].sum() == original["is_printed"].sum()
    assert set(df.loc[df["ifc_class"] == "IfcSlabStandardCase", "class_family"]) == {"IfcSlab"}


def test_exception_per_window_acts_on_opening(mfh):
    """Ein Fenster «nicht drucken» wird ausgeschnitten, auch wenn der Fenstermodus «geschlossen» ist (B-10)."""
    ifc, df = mfh
    kw = dict(scale=200, pitch_mm=QUALITIES["entwurf"], profile=PROFILE, material=MATERIAL,
              windows="geschlossen", doors="geschlossen")
    windows = {f.guid for f in ifc.filler if f.kind == "windows"}
    full = pipeline.generate(ifc, df, **kw)
    is_open = pipeline.generate(ifc, df, exceptions={g: "entfernen" for g in windows}, **kw)
    assert is_open.volume_cm3 < full.volume_cm3
    assert is_open.watertight


def test_checklist_reports_silent_cases(mfh):
    ifc, df = mfh
    hints = pipeline.checklist(ifc, df)
    assert any("IfcFurniture" in h for h in hints)
    assert not any("Landeskoordinaten" in h for h in hints)


def test_surroundings_appear_in_the_checklist(mfh):
    """Als Umgebung erkannte Bauteile fehlen im Druck und werden deshalb gemeldet (Blatt 05, PDF)."""
    ifc, df = mfh
    with_surroundings = df.copy()
    with_surroundings.loc[with_surroundings.index[:3], ["action", "category", "is_printed"]] = ["entfernen", "Umgebung", False]
    count = int((with_surroundings["category"] == "Umgebung").sum())
    points = [p for p in pipeline.check_points(ifc, with_surroundings) if p["kind"] == "umgebung"]
    assert len(points) == 1 and points[0]["category"] == "umgebung"
    assert points[0]["title"].startswith(f"{count} Bauteile als Umgebung")


def test_quality_auto(mfh, monkeypatch):
    ifc, df = mfh
    assert pipeline.resolve_quality("entwurf", ifc, df, 200) == (0.8, None)
    pitch, note = pipeline.resolve_quality("auto", ifc, df, 200)
    assert pitch == 0.4 and "fein" in note
    monkeypatch.setattr(pipeline, "grid_limit", lambda: 1000)          # kleiner Rechner
    pitch, note = pipeline.resolve_quality("auto", ifc, df, 50)
    assert pitch == 0.8 and note.startswith("Qualität automatisch: entwurf")


def test_storey_selection(mfh):
    ifc, df = mfh
    ground_floor = df.loc[df["is_printed"], "storey"].value_counts().index[0]
    only = pipeline.analyse(ifc, Ruleset.default(), 200, PROFILE, storeys=[ground_floor])
    assert set(only.loc[only["is_printed"], "storey"]) == {ground_floor}
    assert (only["category"] == "Geschoss abgewählt").sum() == int((df["is_printed"] & (df["storey"] != ground_floor)).sum())
    u_all, u_ground_floor = (pipeline.model_overview(ifc, d, 200, PROFILE) for d in (df, only))
    assert u_ground_floor["model_mm"][2] < u_all["model_mm"][2]                 # Bauraum nur über die Auswahl


def test_storey_selection_generates_only_the_selected_storey(mfh):
    """Nur ein oberes Geschoss gewählt: genau ein Teil, keine hauchdünnen Teile der abgewählten Geschosse."""
    ifc, _ = mfh
    only = pipeline.analyse(ifc, Ruleset.default(), 200, PROFILE, storeys=["2. OG"])
    res = pipeline.generate(ifc, only, scale=200, pitch_mm=QUALITIES["entwurf"], profile=PROFILE, material=MATERIAL)
    assert list(res.parts) == ["2. OG"]
    assert res.parts["2. OG"].extents[2] > 5                              # ganzes Geschoss samt Decke


def test_plug_connector_clearance_from_printer_profile(mfh):
    """Das Passungsspiel kommt aus dem Profil (clearance_mm); fehlt es, gilt config.CLEARANCE_MM (0.20 mm)."""
    ifc, df = mfh
    res = pipeline.generate(ifc, df, scale=200, pitch_mm=QUALITIES["entwurf"], profile={**PROFILE, "clearance_mm": 0.25},
                            material=MATERIAL, connectors=True)
    assert any("Spiel 0.25 mm" in w for w in res.warnings)


def test_openings_without_windows_are_cut(mfh, monkeypatch):
    """Treppenaugen und Schächte ohne Füller fehlen im Druck nicht mehr (MFH: 7 Deckenöffnungen)."""
    ifc, df = mfh
    kw = dict(scale=200, pitch_mm=QUALITIES["entwurf"], profile=PROFILE, material=MATERIAL)
    assert sum(len(v) for v in ifc.voids.values()) == 7
    with_it = pipeline.generate(ifc, df, **kw)
    assert any("7 Öffnungen ohne Fenster oder Tür" in w for w in with_it.warnings)
    monkeypatch.setattr(type(ifc), "voids", property(lambda self: {}))
    without_it = pipeline.generate(ifc, df, **kw)
    assert with_it.volume_cm3 < without_it.volume_cm3 and with_it.watertight
