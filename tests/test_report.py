"""Tests für den Report: PDF (WeasyPrint, übersprungen ohne Pango) und CSV."""

import pandas as pd
import pytest

from core.output import report
from core.output.report import elements_csv, report_pdf
from core.output.report_data import build_report_data

needs_weasyprint = pytest.mark.skipif(not report.available(), reason="WeasyPrint/Pango fehlt")


def _example_df():
    return pd.DataFrame({
        "ifc_class": ["IfcWall", "IfcColumn", "IfcSlab"],
        "storey": ["EG", "EG", "OG"],
        "status": ["druckbar", "kritisch", "druckbar"],
        "thickness_model_mm": [1.2, 0.9, 1.5],
        "filament_g": [10.0, 5.0, 8.0],
        "name": ["Wand", "Stütze", "Decke"],
        "action": ["behalten", "verdicken", "behalten"],
        "rule": ["IfcWall", "IfcColumn", ""],
        "is_printed": [True, True, False],
    })


@needs_weasyprint
def test_pdf_starts_with_magic_bytes(report_context):
    pdf = report_pdf(build_report_data(_example_df(), report_context, None, []))
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


@needs_weasyprint
def test_pdf_without_data(report_context):
    df = _example_df().iloc[0:0]
    assert report_pdf(build_report_data(df, report_context, None, []))[:4] == b"%PDF"


@needs_weasyprint
def test_pdf_without_thicknesses(report_context):
    df = _example_df().assign(thickness_model_mm=float("nan"))
    assert report_pdf(build_report_data(df, report_context, None, []))[:4] == b"%PDF"


@needs_weasyprint
def test_pdf_escapes_project_name(report_context):
    """Projektname mit Anführungszeichen und Spitzklammern landet im Kopfband (CSS) und im Text (HTML)."""
    report_context["ifc_meta"]["projekt"] = 'Haus "A" </style><b>'
    assert report_pdf(build_report_data(_example_df(), report_context, None, []))[:4] == b"%PDF"


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
