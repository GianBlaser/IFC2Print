"""Auswertungen der Bauteiltabelle für die Oberfläche: Kennzahlen, Geschoss-Matrix, Klassen ohne Regel, Prüfbericht.

Zweck:   Rechnet aus der Bauteiltabelle der Analyse (DataFrame) die Zahlen und Listen, die Panel, Matrix, Regelblatt
         und Prüfbericht zeigen. Reine Funktionen ohne Sitzung und ohne Oberfläche – so ist jede einzeln lesbar und
         prüfbar. ui/state.py reicht sie über die gleichnamigen Methoden von Session an die Seite weiter.
Eingabe: Bauteiltabelle (``df``, von core.pipeline.analyse), bei Bedarf IFC-Modell, Regeln oder Prüfpunkte
Ausgabe: Kennzahlen (dict), Matrix-Zeilen und Klassenlisten (list[dict]), Massstab-Vorschlag, Prüfbericht als PDF-Bytes
"""

import pandas as pd

from config import SCALES
from core import pipeline
from core.ifc.model import IfcModel
from core.output import report

PRINT_STATUSES = ("druckbar", "kritisch", "nicht_druckbar")   # Druckbarkeitsstatus der gedruckten Bauteile


def metrics(df: pd.DataFrame | None) -> dict[str, int]:
    """Kennzahlen: gedruckte Bauteile gesamt, nicht gedruckte und je Druckbarkeitsstatus (ohne Modell: leer)."""
    if df is None:
        return {}
    printed = df[df["is_printed"]]
    status = printed["status"].value_counts()
    return {"total": len(printed), "nicht_gedruckt": len(df) - len(printed),
            **{s: int(status.get(s, 0)) for s in PRINT_STATUSES}}


def status_matrix(ifc: IfcModel | None, df: pd.DataFrame | None) -> list[dict]:
    """Je Geschoss (Reihenfolge wie pipeline.storey_order): Anzahl ok / kritisch / nicht druckbar / nicht gedruckt."""
    if df is None:
        return []
    rows = []
    for storey in pipeline.storey_order(ifc, df):
        part = df[df["storey"] == storey]
        printed = part[part["is_printed"]]["status"].value_counts()
        rows.append({"storey": storey, "nicht_gedruckt": int((~part["is_printed"]).sum()),
                     **{s: int(printed.get(s, 0)) for s in PRINT_STATUSES}})
    return rows


def classes_without_rule(df: pd.DataFrame | None, rules: list[dict]) -> list[dict]:
    """Klassen des Modells ohne eigene Regel im Regelset: [{ifc_class_name, rule, action, category, count}].

    ``rule`` ist der Schlüssel, der stattdessen gilt (geerbt, z.B. IfcSlab), «» = keine Regel.
    Sichtbar im Regelblatt – früher wurden solche Klassen still entfernt.
    """
    if df is None:
        return []
    own_classes = {r["ifc_class_name"].split(".")[0] for r in rules}
    result = []
    for ifc_class, class_group in df[~df["ifc_class"].isin(own_classes)].groupby("ifc_class"):
        without_aggregate = class_group[class_group["aggregate"] == ""] if "aggregate" in class_group else class_group
        row = (without_aggregate if len(without_aggregate) else class_group).iloc[0]
        result.append({"ifc_class_name": ifc_class, "rule": row["rule"], "action": row["action"],
                       "category": row["category"] if row["rule"] else "Sonstiges", "count": len(class_group)})
    return result


def scale_suggestion(overview: dict, current: int, margin: float = 0.9) -> tuple[str, float] | None:
    """Kleinster Massstab-Sprung, bei dem alle Achsen ≤ ``margin`` des Bauraums liegen: (Name, Höhe mm).

    ``current`` ist der heutige Nenner (200 für 1:200); ``overview`` kommt von core.pipeline.model_overview.
    """
    if overview.get("dimensions_m") is None:
        return None
    for name, denominator in sorted(SCALES.items(), key=lambda kv: kv[1]):
        if denominator <= current:
            continue
        model = [mm * current / denominator for mm in overview["model_mm"]]
        if all(m <= margin * b for m, b in zip(model, overview["bauraum_mm"])):
            return name, model[2]
    return None


def check_point_sentence(point: dict) -> str:
    """Ein Prüfpunkt als Satz für den Bericht: «Titel: Eintrag (Anzahl), …» bzw. «Titel. Erklärung»."""
    if not point["entries"]:
        return f"{point['title']}. {point['explanation']}"
    entries = ", ".join(text if count is None else f"{text} ({count})" for text, count in point["entries"])
    return f"{point['title']}: {entries}"


def check_report_pdf(ifc: IfcModel, df: pd.DataFrame, filename: str, scale: str, check_points: list[dict]) -> bytes:
    """Prüfbericht ohne Druckteil: Kennzahlen der Analyse und alle Prüfpunkte."""
    k = metrics(df)
    summary = {"Datei": filename, "Schema": ifc.schema, "Massstab": scale,
               "Bauteile": len(df), "Gedruckt": k["total"], "Kritisch": k["kritisch"],
               "Nicht druckbar": k["nicht_druckbar"], "Nicht gedruckt": k["nicht_gedruckt"]}
    return report.report_pdf(df, summary, {}, [check_point_sentence(p) for p in check_points])
