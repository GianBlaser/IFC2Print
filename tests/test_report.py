"""Tests für den Report."""

import pandas as pd

from core.output.report import elements_csv, report_pdf


def _example_df():
    return pd.DataFrame({
        "ifc_class": ["IfcWall", "IfcColumn", "IfcSlab"],
        "storey": ["EG", "EG", "OG"],
        "status": ["druckbar", "kritisch", "druckbar"],
        "thickness_model_mm": [1.2, 0.9, 1.5],
        "filament_g": [10.0, 5.0, 8.0],
    })


def test_pdf_starts_with_magic_bytes():
    pdf = report_pdf(_example_df(), {"Schema": "IFC2x3", "Massstab": "1:200"},
                     {"EG": 15.0, "OG": 8.0})
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_pdf_without_data():
    df = pd.DataFrame({"status": pd.Series([], dtype=str), "thickness_model_mm": pd.Series([], dtype=float)})
    pdf = report_pdf(df, {}, {})
    assert pdf[:4] == b"%PDF"


def test_pdf_without_thicknesses():
    df = _example_df().assign(thickness_model_mm=float("nan"))
    assert report_pdf(df, {"Schema": "IFC4"}, {"EG": 1.0})[:4] == b"%PDF"


def test_csv_contains_header():
    csv = elements_csv(_example_df())
    assert b"klasse" in csv and b"ifc_class" not in csv         # Kopfzeile deutsch wie vor der Umbenennung
    assert b"IfcWall" in csv


def test_csv_utf8_with_bom():
    df = pd.DataFrame({"ifc_class": ["IfcWall"], "category": ["Öffnung"]})
    csv = elements_csv(df)
    assert csv.startswith(b"\xef\xbb\xbf")
    assert "Öffnung" in csv.decode("utf-8-sig")


def test_csv_without_index():
    rows = elements_csv(_example_df()).decode("utf-8-sig").splitlines()
    assert rows[0].startswith("klasse,")
    assert len(rows) == 4
