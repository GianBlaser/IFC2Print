"""Tests für die Druckbarkeits-Logik."""

import numpy as np
import pandas as pd

from core.analysis.printability import check, CRITICAL, NOT_PRINTABLE, PRINTABLE, status


def test_constants():
    assert (PRINTABLE, CRITICAL, NOT_PRINTABLE) == ("druckbar", "kritisch", "nicht_druckbar")


def test_status_printable():
    assert status(1.5) == PRINTABLE


def test_status_critical():
    assert status(1.0) == CRITICAL


def test_status_not_printable():
    assert status(0.3) == NOT_PRINTABLE


def test_status_scalar_is_str():
    assert isinstance(status(1.5), str)


def test_status_nan_not_printable():
    assert status(float("nan")) == NOT_PRINTABLE


def test_status_array():
    out = status(np.array([1.5, 1.0, 0.3, np.nan]))
    assert list(out) == [PRINTABLE, CRITICAL, NOT_PRINTABLE, NOT_PRINTABLE]


def test_status_own_min_wall():
    assert status(1.0, min_wall_mm=1.0) == CRITICAL
    assert status(1.5, min_wall_mm=1.0) == PRINTABLE
    assert status(0.9, min_wall_mm=1.0) == NOT_PRINTABLE


def _element_df():
    """Drei Bauteile in realen mm plus eins ohne Geometrie (NaN)."""
    return pd.DataFrame({
        "ifc_class":       ["IfcWall", "IfcSlab", "IfcColumn", "IfcSpace"],
        "bbox_x_mm":    [5000.0, 8000.0, 300.0, np.nan],
        "bbox_y_mm":    [300.0, 6000.0, 300.0, np.nan],
        "bbox_z_mm":    [3000.0, 200.0, 3000.0, np.nan],
        "thickness_min_mm": [300.0, 200.0, 400.0, np.nan],
    })


def test_check_scale_200():
    df = check(_element_df(), 200)
    # 300/200 = 1.5 → druckbar; 200/200 = 1.0 → kritisch; 400/200 = 2.0 → druckbar
    assert list(df["status"]) == [PRINTABLE, CRITICAL, PRINTABLE, NOT_PRINTABLE]
    assert np.allclose(df["thickness_model_mm"].iloc[:3], [1.5, 1.0, 2.0])
    assert np.isnan(df.loc[3, "thickness_model_mm"])


def test_check_returns_copy():
    df = _element_df()
    check(df, 200)
    assert "status" not in df.columns


def test_layer_thickness_is_preferred_for_status():
    """Dünne BBox-Kante, aber dickes Schichtpaket → über das Paket bewertet.

    40 mm (thickness_min_mm) wären 1:200 = 0.2 mm → nicht_druckbar.
    Mit layer_thickness_mm = 400 (ganzes Wandpaket) sind es 2.0 mm → druckbar.
    """
    df = pd.DataFrame({
        "ifc_class":           ["IfcWall"],
        "bbox_x_mm":        [5000.0],
        "bbox_y_mm":        [40.0],
        "bbox_z_mm":        [3000.0],
        "thickness_min_mm":     [40.0],
        "layer_thickness_mm": [400.0],
    })
    out = check(df, 200)
    assert out.loc[0, "status"] == PRINTABLE
    assert abs(out.loc[0, "thickness_model_mm"] - 2.0) < 1e-9


def test_layer_thickness_nan_falls_back_to_bbox():
    df = _element_df().assign(layer_thickness_mm=[np.nan, 400.0, np.nan, np.nan])
    out = check(df, 200)
    assert list(out["thickness_model_mm"].iloc[:3]) == [1.5, 2.0, 2.0]
    assert list(out["status"]) == [PRINTABLE, PRINTABLE, PRINTABLE, NOT_PRINTABLE]


def test_without_layer_column_fallback_bbox():
    df = check(_element_df(), 200)
    assert list(df["status"]) == [PRINTABLE, CRITICAL, PRINTABLE, NOT_PRINTABLE]


def test_build_volume_default_profile():
    df = check(_element_df(), 200)
    # Wand 1:200 = 25 x 1.5 x 15 mm passt, Decke 40 x 30 x 1 mm passt; NaN passt nicht
    assert list(df["fits_in_build_volume"]) == [True, True, True, False]


def test_build_volume_from_profile():
    profile = {"build_volume_x_mm": 20.0, "build_volume_y_mm": 100.0, "build_volume_z_mm": 100.0}
    df = check(_element_df(), 200, profile)
    # Wand 25 mm in x passt nicht mehr, Stütze 1.5 x 1.5 x 15 mm schon
    assert list(df["fits_in_build_volume"]) == [False, False, True, False]


def test_build_volume_oversized_element():
    df = pd.DataFrame({"bbox_x_mm": [300.0 * 100], "bbox_y_mm": [1000.0], "bbox_z_mm": [1000.0],
                       "thickness_min_mm": [1000.0]})
    assert not check(df, 100).loc[0, "fits_in_build_volume"]   # 300 mm > 250 mm


def test_min_wall_from_profile():
    df = check(_element_df(), 200, {"min_wall_mm": 1.5})
    # 1.5 → kritisch (< 1.9), 1.0 → nicht_druckbar, 2.0 → druckbar
    assert list(df["status"]) == [CRITICAL, NOT_PRINTABLE, PRINTABLE, NOT_PRINTABLE]


def test_status_exactly_on_the_limits():
    """240 mm bei 1:200 = 1.2 mm liegt exakt auf der Grenze druckbar/kritisch (Fliesskomma)."""
    assert status(240 / 200) == PRINTABLE
    assert status(160 / 200) == CRITICAL
    assert status(159 / 200) == NOT_PRINTABLE


def test_geometry_ok_missing_defective():
    df = pd.DataFrame({
        "bbox_x_mm": [5000.0, np.nan, 5000.0], "bbox_y_mm": [200.0, np.nan, 0.0],
        "bbox_z_mm": [3000.0, np.nan, 3000.0], "thickness_min_mm": [200.0, np.nan, 0.0]})
    assert list(check(df, 200)["geometry"]) == ["ok", "fehlt", "defekt"]
