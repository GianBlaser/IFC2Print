"""Report-Daten: alle Werte des PDF-Reports fertig formatiert, damit das Template nichts rechnet.

Zweck:   Übersetzt Bauteiltabelle, Modell-Info, Ergebnis und Prüfpunkte in die Abschnitte des Übergabeblatts:
         Kopf, Kenndaten, Urteil, Druckteile (Seite 1), Regelwerk, Druckbarkeit je Klasse, Prüfpunkte (Seite 2)
         und die Bauteiltabelle (Anhang). Ohne Ergebnis (Prüfbericht) entfallen Urteil, Druckteile und Modellbild.
Eingabe: Bauteiltabelle, Kontext der Sitzung (``report_context``), ``Result`` oder None, Prüfpunkte
Ausgabe: ``ReportData`` (Texte, Zahlen, Farben, Modellbild als PNG) für core/output/report.py
"""

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.ifc.model import IfcModel
from core.output import preview
from core.output.model_info import model_overview
from core.output.report_image import model_png
from core.output.view_data import storey_order

# Regelwerk-Balken: (Aktion, Beschriftung, Farbe); «ohne Regel» zählt alle Bauteile mit leerer Regel
_DECISIONS = (("behalten", "behalten", "#17191C"), ("verdicken", "verdicken", "#FF6B2C"),
              ("fuellen", "füllen", "#F2A93B"), ("band", "als Band", "#2CC6C6"),
              ("entfernen", "entfernen", "#7B8594"))
_WITHOUT_RULE = ("ohne Regel", "#D03B40")
# Aktion als Text (Druckbarkeit je Klasse, Anhang): (Beschriftung, Farbe)
_ACTION_TEXT = {"behalten": ("behalten", "#17191C"), "verdicken": ("verdicken", "#C94A12"),
                "fuellen": ("füllen", "#B4690E"), "band": ("als Band", "#C94A12"),
                "entfernen": ("entfernen", "#7B8594")}
_NO_RULE_TEXT = ("keine Regel", "#D03B40")
MAX_CLASSES = 13                                   # Zeilen «Druckbarkeit je IFC-Klasse», danach eine Schlusszeile

# Stufe je Art des Prüfpunkts (alles andere: info), Gruppen in dieser Reihenfolge: (Titel, Akzent, Textfarbe)
LEVEL = {"keine": "err", "geometry": "err", "geerbt": "warn", "ausreisser": "warn", "umgebung": "warn"}
_GROUPS = {"err": ("Handlungsbedarf", "#D03B40", "#B02E33"), "warn": ("Prüfen", "#B4690E", "#8F5208"),
           "info": ("Zur Kenntnis", "#7B8594", "#4F5662")}
_MARK = {"ok": "✓", "warn": "!", "err": "!"}


@dataclass
class ReportData:
    """Inhalt des PDF-Reports, fertig formatiert."""
    head: dict                    # projekt, datei, schema, datum, massstab, regelset, total, printed, parts_n, Titel
    specs: list[dict]             # Seitenleiste Seite 1: {key, value, icon, icon_data, nowrap}
    image_png: bytes | None       # Modellansicht; None = noch nicht erzeugt
    verdict: list[dict] | None    # None = Prüfbericht ohne Ergebnis
    parts: list[dict]             # Druckteile
    decisions: list[dict]         # Regelwerk-Balken
    classes: list[dict]           # Druckbarkeit je IFC-Klasse (höchstens MAX_CLASSES)
    classes_more: str | None      # Schlusszeile, wenn es mehr Klassen gibt
    check_groups: list[dict]      # Prüfpunkte nach Stufe
    check_summary: str            # «6 PUNKTE · 2 MIT HANDLUNGSBEDARF»
    elements: list[dict]          # Anhang: alle Bauteile


def report_context(ifc: IfcModel, df: pd.DataFrame, filename: str, *, scale: int, ruleset_name: str,
                   profile: dict, material: dict, angle: float = 0.0, windows: str = "geschlossen",
                   doors: str = "geschlossen") -> dict:
    """Was der Report aus der Sitzung braucht: IFC-Kopfdaten, Abmessungen (model_overview) und Einstellungen."""
    overview = model_overview(ifc, df, scale, profile, angle)
    projects = ifc.model.by_type("IfcProject")
    meta = {"projekt": (projects[0].Name if projects else "") or Path(filename).stem, "datei": filename,
            "schema": ifc.schema, "storeys": storey_order(ifc, df), "real_m": overview.get("dimensions_m"),
            "model_mm": overview.get("model_mm"), "bauraum_mm": overview["bauraum_mm"],
            "fits": overview.get("fits", True), "rotated": overview.get("rotated", False),
            "recommendation": overview.get("recommendation")}
    return {"ifc_meta": meta, "scale": scale, "ruleset_name": ruleset_name, "profile": profile,
            "material": material, "angle": angle, "windows": windows, "doors": doors}


def build_report_data(df: pd.DataFrame, context: dict, result, check_points: list[dict]) -> ReportData:
    """Alle Abschnitte des Reports; ``result`` = ``Result`` oder None (Prüfbericht).

    Mit Ergebnis gelten die Einstellungen des Laufs (``result.settings``), sonst die des Kontexts.
    ``check_points``: die für den Druck relevanten Prüfpunkte (core.analysis.check_points.for_print).
    """
    settings = {**context, **(result.settings if result is not None else {})}
    meta = context["ifc_meta"]
    parts = _parts(result) if result is not None else []
    return ReportData(
        head=_head(df, meta, settings, context["ruleset_name"], result),
        specs=_specs(meta, settings, result),
        image_png=model_png(result.print_parts, result.overhang_marks, {p["name"]: p["color"] for p in parts})
        if result is not None else None,
        verdict=_verdict(df, meta, settings, result) if result is not None else None,
        parts=parts,
        decisions=_decisions(df),
        **_classes(df),
        **_checks(check_points),
        elements=_elements(df, meta.get("storeys", [])),
    )


# --- Formate --------------------------------------------------------------------

def count_text(n: int) -> str:
    """Anzahl ohne Tausendertrenner bis 9999, ab 10 000 mit Apostroph (10'000)."""
    return str(n) if n < 10_000 else f"{n:,}".replace(",", "'")


def _missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def mm_text(value, decimals: int) -> str:
    """Länge in mm mit ``decimals`` Nachkommastellen, fehlend (NaN) als «–»."""
    return "–" if _missing(value) else f"{value:.{decimals}f}"


def angle_text(angle: float) -> str:
    return f"{angle:.1f}°"


def _percent(part: int, total: int) -> str:
    return f"{100 * part / total:.3f}%" if total else "0%"


def _mix(color: str, share: float) -> str:
    """Farbe ``share`` (0..1) auf Weiss – WeasyPrint kennt kein color-mix()."""
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(255 - share * (255 - c)):02X}" for c in rgb)


# --- Seite 1 --------------------------------------------------------------------

def _head(df: pd.DataFrame, meta: dict, settings: dict, ruleset_name: str, result) -> dict:
    scale = f"1:{settings['scale']}"
    printed = int(df["is_printed"].sum()) if "is_printed" in df else 0
    if result is None:
        title = f"Prüfbericht {scale}"
    else:
        n = len(result.print_parts)
        title = f"Druckmodell {scale}, {n} {'Teil' if n == 1 else 'Teile'}"
    return {"projekt": meta["projekt"], "datei": meta["datei"], "schema": meta["schema"],
            "datum": datetime.now().strftime("%d.%m.%Y %H:%M"), "massstab": scale, "regelset": ruleset_name,
            "total": count_text(len(df)), "printed": count_text(printed),
            "parts_n": len(result.print_parts) if result is not None else 0, "title": title,
            "rules_title": f"{count_text(len(df))} Bauteile im IFC, {count_text(printed)} gedruckt"}


def _spec(key: str, value: str, icon: str | None = None, nowrap: bool = False, **icon_data) -> dict:
    return {"key": key, "value": value, "icon": icon, "icon_data": icon_data, "nowrap": nowrap}


def _specs(meta: dict, settings: dict, result) -> list[dict]:
    """Kenndaten der Seitenleiste; ohne Ergebnis «–» für alles, was erst der Lauf festlegt."""
    profile, material = settings["profile"], settings["material"]
    nozzle, angle = profile.get("nozzle_mm", 0.4), settings.get("angle", 0.0)
    windows, doors = settings.get("windows", "geschlossen"), settings.get("doors", "geschlossen")
    pitch = settings.get("pitch_mm") if result is not None else None
    real = meta.get("real_m")
    if result is None:
        connectors = "–"
    elif result.connector_count:
        connectors = f"{result.connector_count} an {result.joint_count} Fuge{'' if result.joint_count == 1 else 'n'}"
    else:
        connectors = "keine"
    return [
        _spec("SCHEMA", meta["schema"]),
        _spec("MASSSTAB", f"1:{settings['scale']}", "massstab"),
        _spec("DRUCKER", f"{profile['name']}\nDüse {nozzle:.1f} mm", "duese", text=f"{nozzle:.2f} mm"),
        _spec("MATERIAL", material["name"]),
        _spec("VOXEL-PITCH", f"{pitch:.2f} mm", "voxel", text=f"{pitch:.1f} mm") if pitch
        else _spec("VOXEL-PITCH", "–"),
        _spec("AUSRICHTUNG", angle_text(angle), "winkel", rotate=-angle),
        _spec("FENSTER · TÜREN", windows if windows == doors else f"{windows} · {doors}", "oeffnungen",
              windows=windows, doors=doors),
        _spec("MODELL REAL", f"{real[0]:.1f} × {real[1]:.1f} × {real[2]:.1f} m" if real else "–", nowrap=True),
        _spec("STECKVERBINDER", connectors, "verbinder" if result is not None and result.connector_count else None),
        _spec("ÖFFNUNGEN", f"{result.metrics.get('Öffnungen', 0)} eingesetzt" if result is not None else "–"),
    ]


def _verdict_row(level: str, title: str, value: str, sub: str) -> dict:
    return {"level": level, "mark": _MARK[level], "title": title, "value": value, "sub": sub}


def _verdict(df: pd.DataFrame, meta: dict, settings: dict, result) -> list[dict]:
    """Urteil in vier Zeilen: druckbar, wasserdicht, passt aufs Druckbett, Stützen."""
    min_wall = settings["profile"].get("min_wall_mm", 0.8)
    printed = df[df["is_printed"]]
    # Ohne Massnahme bleiben zu dünne Bauteile mit «behalten» ausserhalb von Paketen; Pakete skaliert die Erzeugung
    # auf die Mindestdicke (core/voxels/elements.py), auch wenn ihre Bauteile «behalten» heissen
    outside_package = printed["package"] < 0 if "package" in printed else True
    weak = int(((printed["status"] == "nicht_druckbar") & (printed["action"] == "behalten") & outside_package).sum())
    printable = _verdict_row("ok", "Druckbar", count_text(len(printed)),
                             f"alle gedruckten Bauteile ≥ {min_wall:.1f} mm, "
                             f"{result.metrics.get('Verdickt', 0)} dafür verdickt") if not weak else \
        _verdict_row("warn", "Druckbar", count_text(len(printed)),
                     f"{weak} Bauteil{'' if weak == 1 else 'e'} unter {min_wall:.1f} mm ohne Massnahme")

    leaky, n = result.leaky_parts, len(result.print_parts)
    watertight = _verdict_row("ok" if not leaky else "err", "Wasserdicht", f"{n - len(leaky)} / {n}",
                              "alle Teile auch nach dem STL-Export geschlossen" if not leaky
                              else "nicht dicht: " + ", ".join(leaky))

    model, bed = meta.get("model_mm"), meta["bauraum_mm"]
    size = "×".join(f"{v:.0f}" for v in model) if model else "–"
    if meta.get("fits", True):
        fits = _verdict_row("ok", "Passt aufs Druckbett", size,
                            "mm, Bauraum " + " × ".join(f"{v:.0f}" for v in bed) + " mm"
                            + (", Modell 90° gedreht" if meta.get("rotated") else ""))
    else:
        recommendation = meta.get("recommendation")
        fits = _verdict_row("err", "Passt aufs Druckbett", size,
                            f"Massstab 1:{recommendation} würde passen" if recommendation
                            else "auch im kleinsten Massstab zu gross")

    relevant = [o for o in result.overhangs if o.relevant]
    if relevant:
        names = [result.support_elements.get(o.name, o.name) for o in relevant]
        supports = _verdict_row("warn", "Stützen nötig", f"{sum(o.support_mm2 for o in relevant) / 100:.1f} cm²",
                                ", ".join(dict.fromkeys(names)))
    else:
        supports = _verdict_row("ok", "Keine Stützen", "–", "alle Teile ohne Stützen druckbar")
    return [printable, watertight, fits, supports]


def _parts(result) -> list[dict]:
    """Druckteile in Geschossreihenfolge mit Farbe, Grösse, Stützfläche und Zapfen."""
    supports = {o.name: o.support_mm2 for o in result.overhangs if o.relevant}
    rows = []
    for rank, (name, mesh) in enumerate(result.print_parts.items()):
        pegs = result.pegs_per_part.get(name, 0)
        rows.append({"name": name, "color": preview.storey_color(rank),
                     "size": " × ".join(f"{v:.0f}" for v in mesh.extents),
                     "support": f"{supports[name] / 100:.1f} cm²" if name in supports else "–",
                     "has_support": name in supports, "pegs": f"{pegs} Zapfen" if pegs else "–"})
    return rows


# --- Seite 2 --------------------------------------------------------------------

def _rule_given(df: pd.DataFrame) -> pd.Series:
    return df["rule"].fillna("") != "" if "rule" in df else pd.Series(True, index=df.index)


def _decisions(df: pd.DataFrame) -> list[dict]:
    """Regelwerk-Balken in fester Reihenfolge; die Summe ergibt immer len(df)."""
    given = _rule_given(df)
    action = df["action"] if "action" in df else pd.Series("", index=df.index)
    counts = [(label, color, int((given & (action == key)).sum())) for key, label, color in _DECISIONS]
    counts.append((*_WITHOUT_RULE, len(df) - sum(n for *_, n in counts)))   # leere Regel (oder unbekannte Aktion)
    return [{"label": label, "color": color, "n": count_text(n), "count": n, "width": _percent(n, len(df))}
            for label, color, n in counts]


def _actions(group: pd.DataFrame) -> list[dict]:
    """Vorkommende Aktionen einer Klasse in fester Reihenfolge (nur Bauteile mit Regel), sonst «keine Regel»."""
    with_rule = group[_rule_given(group)]
    present = set(with_rule["action"]) if "action" in with_rule else set()
    actions = [_ACTION_TEXT[key] for key, _, _ in _DECISIONS if key in present]
    return [{"label": label, "color": color} for label, color in actions or [_NO_RULE_TEXT]]


def _classes(df: pd.DataFrame) -> dict:
    """Druckbarkeit je IFC-Klasse: Klassen mit gedruckten Bauteilen zuerst, je absteigend nach Anzahl."""
    rows = []
    for ifc_class, group in df.groupby("ifc_class"):
        printed = group[group["is_printed"]]
        status = printed["status"].value_counts()
        n = len(group)
        counts = {"ok": int(status.get("druckbar", 0)), "kr": int(status.get("kritisch", 0)),
                  "ni": int(status.get("nicht_druckbar", 0)), "sk": n - len(printed)}
        rows.append({"ifc_class": ifc_class, "n": n, "count": count_text(n), "has_printed": len(printed) > 0,
                     **{f"{k}_width": _percent(v, n) for k, v in counts.items()}, "actions": _actions(group)})
    rows.sort(key=lambda r: (not r["has_printed"], -r["n"], r["ifc_class"]))
    rest = rows[MAX_CLASSES:]
    more = (f"+ {len(rest)} weitere {'Klasse' if len(rest) == 1 else 'Klassen'} "
            f"({count_text(sum(r['n'] for r in rest))} Bauteile) – siehe Anhang") if rest else None
    return {"classes": rows[:MAX_CLASSES], "classes_more": more}


def level(point: dict) -> str:
    """Stufe eines Prüfpunkts: err | warn | info."""
    return LEVEL.get(point["kind"], "info")


def _checks(points: list[dict]) -> dict:
    """Prüfpunkte gruppiert nach Stufe (Handlungsbedarf, Prüfen, Zur Kenntnis) und die Zusammenfassung."""
    groups = []
    for key, (title, accent, ink) in _GROUPS.items():
        items = [{"title": p["title"],
                  "entries": " · ".join(t if n is None else f"{t} ({n})" for t, n in p["entries"]) or p["explanation"],
                  "count": count_text(sum(1 if n is None else n for _, n in p["entries"])) if p["entries"] else "–",
                  "fix": p.get("fix", "Keine Aktion")}
                 for p in points if level(p) == key]
        if items:
            groups.append({"level": key, "title": title, "count": len(items), "ink": ink,
                           "background": _mix(accent, 0.07), "head_background": _mix(accent, 0.14), "points": items})
    errors = sum(g["count"] for g in groups if g["level"] == "err")
    summary = f"{len(points)} PUNKTE" + (f" · {errors} MIT HANDLUNGSBEDARF" if errors else "") if points else ""
    return {"check_groups": groups, "check_summary": summary}


# --- Anhang ---------------------------------------------------------------------

def _real_thickness(row) -> float:
    """Massgebende Dicke real: Paket, sonst Schicht, sonst kleinste Abmessung."""
    for column in ("package_thickness_mm", "layer_thickness_mm", "thickness_min_mm"):
        value = row.get(column)
        if not _missing(value):
            return value
    return math.nan


def _elements(df: pd.DataFrame, storeys: list[str]) -> list[dict]:
    """Alle Bauteile, sortiert nach Geschoss (Reihenfolge ``storeys``), Klasse und Name."""
    rank = {name: i for i, name in enumerate(storeys)}
    rows = df.to_dict("records")
    rows.sort(key=lambda r: (rank.get(r.get("storey"), len(rank)), str(r.get("storey", "")),
                             str(r.get("ifc_class", "")), str(r.get("name", ""))))
    result = []
    for r in rows:
        rule_given = not _missing(r.get("rule", "x")) and r.get("rule", "x") != ""
        label, color = _ACTION_TEXT.get(r.get("action"), _NO_RULE_TEXT) if rule_given else _NO_RULE_TEXT
        result.append({"ifc_class": r.get("ifc_class", ""), "name": r.get("name", "") or "", "storey": r.get("storey", ""),
                       "real": mm_text(_real_thickness(r), 0), "model": mm_text(r.get("thickness_model_mm"), 2),
                       "action": label, "color": color})
    return result
