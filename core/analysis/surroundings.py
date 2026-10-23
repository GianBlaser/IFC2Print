"""Umgebung erkennen: Bauteile, die nicht zum Gebäude gehören.

Eingabe: Bauteiltabelle (Name, Typname, Layer, Klasse, Geschoss, Lage)
Ausgabe: True/False je Bauteil (is_surroundings: Umgebung, outlier: Ausreisser)

Stützmauern, Terrainkanten u.ä. sind in Architekturmodellen oft normale IfcWall –
und heissen nicht immer so (4503: «Aussenwände EG» auf der ArchiCAD-Ebene
«011 Stützwände»). Darum zählen mehrere Hinweise:

  * Stichwort (config.SURROUNDINGS_KEYWORDS) am Wortanfang im Namen, Typnamen oder Layer;
    Wörter aus config.SURROUNDINGS_EXCEPTIONS zählen nicht («Geländer» enthält «Gelände»)
  * Klasse für Gelände und Tiefbau (config.SURROUNDINGS_CLASSES, z.B. IfcGeographicElement)
  * Bauteil direkt im Grundstück (IfcSite) statt in einem Geschoss – nur, wenn das
    Modell überhaupt Geschosse nutzt (sonst läge alles «auf dem Grundstück») und das
    Bauteil im Grundriss überwiegend ausserhalb des Gebäudes liegt (ein Dach, das ein
    Autorentool ins Grundstück legt, bleibt Gebäude)

Zusätzlich ``outlier``: gedruckte Bauteile weit weg vom Gebäude (verschobene
Bibliotheksobjekte, Vermesserpunkte). Sie würden das Voxelgitter riesig machen.

Jeder Fehlentscheid lässt sich je Bauteil in der Oberfläche übersteuern.
"""

import re

import numpy as np
import pandas as pd

from config import (OUTLIER_FACTOR, OUTLIER_MIN_M, SURROUNDINGS_EXCEPTIONS, SURROUNDINGS_CLASSES,
                    SURROUNDINGS_KEYWORDS)

_BOX = ("center_x_mm", "center_y_mm", "bbox_x_mm", "bbox_y_mm")


def _pattern(words) -> re.Pattern:
    """Treffer nur am Wortanfang: «stützwänd» trifft «011 Stützwände», ein Stichwort mitten im Wort zählt nicht."""
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + ")")


def is_surroundings(df: pd.DataFrame, keywords=SURROUNDINGS_KEYWORDS, exceptions=SURROUNDINGS_EXCEPTIONS) -> pd.Series:
    """True je Zeile, wenn das Bauteil zur Umgebung gehört."""
    text = df["name"].fillna("")
    for column_mask in ("type_name", "layer"):
        if column_mask in df:
            text = text + " " + df[column_mask].fillna("")
    text = text.str.lower()
    if exceptions:
        text = text.str.replace(re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, exceptions)) + r")\w*"), " ", regex=True)
    hits = text.str.contains(_pattern(keywords), regex=True)
    if "ifc_class" in df:
        hits |= df["ifc_class"].isin(SURROUNDINGS_CLASSES)
    if "on_site" in df and df["on_site"].mean() < 0.5:
        hits |= df["on_site"].astype(bool) & ~_over_building(df)
    return hits


def _over_building(df: pd.DataFrame, fraction: float = 0.5) -> pd.Series:
    """True je Zeile, deren Grundriss-Box mindestens ``fraction`` innerhalb der Box der Geschoss-Bauteile liegt.

    Ohne Lagespalten (ältere Tabellen) gilt kein Bauteil als «über dem Gebäude».
    """
    if not set(_BOX) <= set(df.columns):
        return pd.Series(False, index=df.index)
    lo = np.stack([df["center_x_mm"] - df["bbox_x_mm"] / 2, df["center_y_mm"] - df["bbox_y_mm"] / 2], axis=1)
    hi = np.stack([df["center_x_mm"] + df["bbox_x_mm"] / 2, df["center_y_mm"] + df["bbox_y_mm"] / 2], axis=1)
    building = ~df["on_site"].astype(bool).to_numpy() & np.isfinite(lo).all(axis=1)
    if not building.any():
        return pd.Series(False, index=df.index)
    g_lo, g_hi = lo[building].min(axis=0), hi[building].max(axis=0)
    overlap_extent = np.clip(np.minimum(hi, g_hi) - np.maximum(lo, g_lo), 0, None).prod(axis=1)
    area = np.maximum((hi - lo).prod(axis=1), 1e-9)
    return pd.Series(np.nan_to_num(overlap_extent / area) >= fraction, index=df.index)


def outlier(df: pd.DataFrame, factor: float = OUTLIER_FACTOR, min_m: float = OUTLIER_MIN_M) -> pd.Series:
    """True je gedrucktem Bauteil, das im Grundriss weit ausserhalb des Gebäudekerns liegt.

    Kern = 10. bis 90. Perzentil der Bauteilmitten (robust gegen die Ausreisser selbst),
    Grösse = grössere Kante des Kerns, mindestens ``min_m``. Ausreisser liegt weiter als
    ``factor`` × Grösse vom Kern entfernt (Abstand Box zu Box).
    """
    result = pd.Series(False, index=df.index)
    if not set(_BOX) <= set(df.columns) or "is_printed" not in df:
        return result
    part = df[df["is_printed"]].dropna(subset=list(_BOX))
    if len(part) < 5:
        return result
    centers = part[["center_x_mm", "center_y_mm"]].to_numpy()
    k_lo, k_hi = np.percentile(centers, 10, axis=0), np.percentile(centers, 90, axis=0)
    size = max(float((k_hi - k_lo).max()), min_m * 1000)
    half = part[["bbox_x_mm", "bbox_y_mm"]].to_numpy() / 2
    distance = np.maximum(np.maximum(k_lo - (centers + half), (centers - half) - k_hi), 0).max(axis=1)
    result[part.index] = distance > factor * size
    return result
