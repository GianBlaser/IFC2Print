"""Tests der Report-Daten (core/output/report_data.py) – ohne WeasyPrint."""

import math
import re
from types import SimpleNamespace

import numpy as np
import pandas as pd
import trimesh

from core.output.report_data import build_report_data, count_text, level, MAX_CLASSES, mm_text


def _df(n_classes: int = 3) -> pd.DataFrame:
    """Bauteiltabelle mit allen Aktionen, einem Bauteil ohne Regel und fehlenden Dicken."""
    rows = [
        ("IfcWall", "Wand UG", "UG", "behalten", "IfcWall", True, "druckbar", 300.0, 1.5),
        ("IfcWall", "Wand EG", "EG", "verdicken", "IfcWall", True, "kritisch", 120.0, 0.6),
        ("IfcSlab", "Decke", "EG", "fuellen", "IfcSlab", True, "druckbar", math.nan, math.nan),
        ("IfcRailing", "Geländer", "OG", "band", "IfcRailing", True, "nicht_druckbar", 40.0, 0.2),
        ("IfcFurniture", "Tisch", "EG", "entfernen", "IfcFurniture", False, "druckbar", 30.0, 0.15),
        ("IfcTank", "Speicher", "UG", "entfernen", "", False, "druckbar", 800.0, 4.0),
    ]
    rows += [(f"IfcProxy{i:02d}", f"Proxy {i}", "OG", "entfernen", f"IfcProxy{i:02d}", False, "druckbar", 10.0, 0.05)
             for i in range(n_classes)]
    return pd.DataFrame(rows, columns=["ifc_class", "name", "storey", "action", "rule", "is_printed", "status",
                                       "thickness_min_mm", "thickness_model_mm"])


def test_decisions_sum_to_all_elements(report_context):
    df = _df()
    data = build_report_data(df, report_context, None, [])
    assert sum(d["count"] for d in data.decisions) == len(df)
    assert [d["label"] for d in data.decisions] == ["behalten", "verdicken", "füllen", "als Band", "entfernen",
                                                    "ohne Regel"]
    assert data.decisions[-1]["count"] == 1                       # IfcTank ohne Regel


def test_decisions_count_unknown_action_without_rule(report_context):
    df = _df().assign(action=lambda d: d["action"].where(d.index != 0, "unbekannt"))
    assert sum(d["count"] for d in build_report_data(df, report_context, None, []).decisions) == len(df)


def test_at_most_13_classes_plus_closing_line(report_context):
    df = _df(n_classes=20)
    data = build_report_data(df, report_context, None, [])
    assert len(data.classes) == MAX_CLASSES
    n_classes = df["ifc_class"].nunique()
    assert data.classes_more.startswith(f"+ {n_classes - MAX_CLASSES} weitere Klassen (")
    assert data.classes_more.endswith("Bauteile) – siehe Anhang")
    assert data.classes[0]["has_printed"] and not data.classes[-1]["has_printed"]   # gedruckte Klassen zuerst


def test_class_actions_and_widths(report_context):
    data = build_report_data(_df(), report_context, None, [])
    rows = {c["ifc_class"]: c for c in data.classes}
    assert [a["label"] for a in rows["IfcWall"]["actions"]] == ["behalten", "verdicken"]
    assert rows["IfcTank"]["actions"] == [{"label": "keine Regel", "color": "#D03B40"}]
    assert rows["IfcWall"]["ok_width"] == "50.000%" and rows["IfcWall"]["kr_width"] == "50.000%"
    assert rows["IfcFurniture"]["sk_width"] == "100.000%"


def test_check_point_levels():
    assert [level({"kind": k}) for k in ("keine", "geometry")] == ["err", "err"]
    assert [level({"kind": k}) for k in ("geerbt", "ausreisser", "umgebung")] == ["warn"] * 3
    assert [level({"kind": k}) for k in ("aggregate", "storeys", "versatz", "oeffnungen", "gefaelle")] == ["info"] * 5


def test_check_groups_and_summary(report_context):
    points = [
        {"kind": "keine", "title": "Ohne Regel", "explanation": "x", "entries": [("IfcTank", 1), ("IfcProxy", 4)],
         "fix": "Regeln im Blatt 03 ergänzen"},
        {"kind": "versatz", "title": "Modell in Landeskoordinaten", "explanation": "Um 2'600 km verschoben.",
         "entries": [], "fix": "Keine Aktion; Lage bleibt im IFC"},
    ]
    data = build_report_data(_df(), report_context, None, points)
    assert data.check_summary == "2 PUNKTE · 1 MIT HANDLUNGSBEDARF"
    err, info = data.check_groups
    assert (err["title"], info["title"]) == ("Handlungsbedarf", "Zur Kenntnis")
    assert err["points"][0]["entries"] == "IfcTank (1) · IfcProxy (4)" and err["points"][0]["count"] == "5"
    assert info["points"][0]["entries"] == "Um 2'600 km verschoben." and info["points"][0]["count"] == "–"
    assert err["background"] == "#FCF1F2"                                  # Akzent 7 % auf Weiss, vorgerechnet
    assert build_report_data(_df(), report_context, None, []).check_summary == ""


def test_formats(report_context):
    data = build_report_data(_df(), report_context, None, [])
    assert re.fullmatch(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}", data.head["datum"])
    assert data.head["massstab"] == "1:200" and data.head["title"] == "Prüfbericht 1:200"
    specs = {s["key"]: s for s in data.specs}
    assert specs["AUSRICHTUNG"]["value"] == "-12.5°" and specs["AUSRICHTUNG"]["icon_data"]["rotate"] == 12.5
    assert specs["FENSTER · TÜREN"]["value"] == "vertieft · geschlossen"
    assert specs["DRUCKER"]["value"] == "Prusa MK4\nDüse 0.4 mm"
    assert specs["MODELL REAL"]["value"] == "12.0 × 8.5 × 6.2 m"
    assert (mm_text(math.nan, 0), mm_text(None, 2), mm_text(1.834, 2)) == ("–", "–", "1.83")
    assert (count_text(1206), count_text(10_000)) == ("1206", "10'000")


def test_elements_sorted_by_storey_with_dash_for_missing_thickness(report_context):
    data = build_report_data(_df(), report_context, None, [])
    assert [e["storey"] for e in data.elements][:3] == ["UG", "UG", "EG"]
    slab = next(e for e in data.elements if e["ifc_class"] == "IfcSlab")
    assert (slab["real"], slab["model"], slab["action"]) == ("–", "–", "füllen")
    tank = next(e for e in data.elements if e["ifc_class"] == "IfcTank")
    assert (tank["real"], tank["action"]) == ("800", "keine Regel")


def test_without_result_no_verdict(report_context):
    data = build_report_data(_df(), report_context, None, [])
    assert data.verdict is None and data.parts == [] and data.image_png is None
    assert {s["key"]: s["value"] for s in data.specs}["STECKVERBINDER"] == "–"


def _result(leaky: list[str]) -> SimpleNamespace:
    """Ergebnis-Attrappe mit zwei Teilen, einem Überhang und Steckverbindern."""
    parts = {"UG": trimesh.creation.box((60, 40, 15)), "EG": trimesh.creation.box((60, 40, 14))}
    overhang = SimpleNamespace(name="EG", support_mm2=130.0, relevant=True)
    return SimpleNamespace(print_parts=parts, overhang_marks={}, overhangs=[overhang], leaky_parts=leaky,
                           support_elements={"EG": "Vordach Süd"}, pegs_per_part={"UG": 6}, connector_count=6,
                           joint_count=1, metrics={"Verdickt": 3, "Öffnungen": 12},
                           settings={"scale": 200, "pitch_mm": 0.4, "angle": 0.0, "windows": "geschlossen",
                                     "doors": "geschlossen", "profile": {"name": "Prusa MK4", "min_wall_mm": 0.8},
                                     "material": {"name": "PLA"}})


def test_verdict_and_parts_with_result(report_context):
    df = _df().assign(status=lambda d: d["status"].where(d.index != 0, "nicht_druckbar"))   # Wand UG, behalten
    data = build_report_data(df, report_context, _result(leaky=["EG"]), [])
    printable, watertight, fits, supports = data.verdict
    assert (printable["level"], printable["sub"]) == ("warn", "1 Bauteil unter 0.8 mm ohne Massnahme")
    assert (watertight["level"], watertight["value"], watertight["sub"]) == ("err", "1 / 2", "nicht dicht: EG")
    assert (fits["level"], fits["value"]) == ("ok", "60×42×31")
    assert (supports["title"], supports["value"], supports["sub"]) == ("Stützen nötig", "1.3 cm²", "Vordach Süd")
    assert data.parts[0] == {"name": "UG", "color": "#5AA9FF", "size": "60 × 40 × 15", "support": "–",
                             "has_support": False, "pegs": "6 Zapfen"}
    assert data.parts[1]["support"] == "1.3 cm²"
    specs = {s["key"]: s["value"] for s in data.specs}
    assert specs["STECKVERBINDER"] == "6 an 1 Fuge" and specs["ÖFFNUNGEN"] == "12 eingesetzt"
    assert specs["MATERIAL"] == "PLA"                                   # Einstellungen des Laufs gelten
    assert data.head["title"] == "Druckmodell 1:200, 2 Teile"
    assert data.image_png[:4] == b"\x89PNG"


def test_thin_elements_in_a_package_count_as_treated(report_context):
    """Pakete werden beim Erzeugen auf die Mindestdicke skaliert – auch mit «behalten» keine offene Massnahme."""
    df = _df().assign(status=lambda d: d["status"].where(d.index != 0, "nicht_druckbar"),
                      package=lambda d: [3 if i == 0 else -1 for i in d.index])
    assert build_report_data(df, report_context, _result(leaky=[]), []).verdict[0]["level"] == "ok"


def test_verdict_bed_too_small(report_context):
    report_context["ifc_meta"].update(fits=False, recommendation=500)
    df = _df().assign(status="druckbar")
    data = build_report_data(df, report_context, _result(leaky=[]), [])
    printable, watertight, fits, _ = data.verdict
    assert printable["level"] == "ok" and printable["sub"] == "alle gedruckten Bauteile ≥ 0.8 mm, 3 dafür verdickt"
    assert watertight["level"] == "ok"
    assert (fits["level"], fits["sub"]) == ("err", "Massstab 1:500 würde passen")
    assert np.isclose(sum(float(d["width"].rstrip("%")) for d in data.decisions), 100.0, atol=0.01)
