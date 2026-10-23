"""Report: PDF (Deckblatt + Diagramme, Matplotlib) und CSV der Bauteiltabelle.

Eingabe: Bauteiltabelle, Kennzahlen und Filament je Teil der Erzeugung
Ausgabe: PDF- bzw. CSV-Datei als Bytes
"""

import io
import textwrap

import matplotlib
matplotlib.use("Agg")   # headless, keine GUI nötig
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

_STATUS_COLOR = {"druckbar": "#1E8A57", "kritisch": "#A86A00", "nicht_druckbar": "#C93434"}


# Die CSV ist wie das PDF eine Ausgabe für Menschen: Kopfzeile deutsch, wie vor der englischen Umbenennung
# der Spalten (Oktober 2026). Spalten ohne Eintrag (guid, name, layer, status, bbox_*) heissen gleich.
CSV_HEADERS = {
    "ifc_class": "klasse", "class_family": "familie", "aggregate": "ganzes", "predefined_type": "typ",
    "type_name": "typname", "storey": "geschoss", "on_site": "auf_grundstueck",
    "center_x_mm": "mitte_x_mm", "center_y_mm": "mitte_y_mm", "center_z_mm": "mitte_z_mm",
    "thickness_min_mm": "dicke_min_mm", "layer_thickness_mm": "schicht_dicke_mm", "mesh_defective": "netz_defekt",
    "action": "aktion", "category": "kategorie", "rule": "regel", "is_printed": "drucken", "package": "paket",
    "package_thickness_mm": "paket_dicke_mm", "thickness_model_mm": "dicke_modell_mm", "geometry": "geometrie",
    "fits_in_build_volume": "passt_in_bauraum",
}


def elements_csv(df: pd.DataFrame) -> bytes:
    """Bauteiltabelle als UTF-8-CSV mit BOM (öffnet in Excel korrekt), Kopfzeile deutsch (CSV_HEADERS)."""
    return df.rename(columns=CSV_HEADERS).to_csv(index=False).encode("utf-8-sig")


def _cover_page(metrics: dict, hints: list[str] = ()):
    fig = plt.figure(figsize=(8.27, 11.69))   # A4 hoch
    fig.suptitle("IFC2Print – Report", fontsize=20, y=0.95)
    fig.text(0.1, 0.88, "\n".join(f"{k}:  {v}" for k, v in metrics.items()),
             fontsize=11, va="top", family="monospace")
    if hints:
        text = "\n".join("• " + "\n  ".join(textwrap.wrap(h, 95)) for h in hints)
        fig.text(0.1, 0.42, "Prüfliste\n" + text, fontsize=8, va="top", family="monospace")
    fig.text(0.1, 0.05, "Filament, Kosten und Druckzeit sind Schätzungen.", fontsize=9, style="italic")
    return fig


def _bar_chart(values: pd.Series, title: str, axis: str, colors=None, horizontal=False):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if values.empty:
        ax.text(0.5, 0.5, "keine Daten", ha="center", va="center")
    elif horizontal:
        ax.barh(values.index.astype(str), values.values, color=colors or "#72B7B2")
        ax.set_xlabel(axis)
    else:
        ax.bar(values.index.astype(str), values.values, color=colors or "#4C78A8")
        ax.set_ylabel(axis)
    ax.set_title(title)
    fig.tight_layout()
    return fig


def _histogram_thicknesses(df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    thicknesses = df["thickness_model_mm"].dropna()
    if len(thicknesses):
        ax.hist(thicknesses, bins=20, color="#E45756")
        ax.set_xlabel("Dicke im Modell (mm)")
        ax.set_ylabel("Anzahl")
    ax.set_title("Bauteildicken im Modellmassstab")
    fig.tight_layout()
    return fig


def report_pdf(df: pd.DataFrame, metrics: dict, filament_per_storey: dict[str, float],
               hints: list[str] = ()) -> bytes:
    printed = df[df["is_printed"]] if "is_printed" in df else df    # Status zählt nur, was gedruckt wird
    status = printed["status"].value_counts()
    figures = (
        _cover_page(metrics, hints),
        _bar_chart(status, "Gedruckte Bauteile je Druckbarkeits-Status", "Anzahl",
                colors=[_STATUS_COLOR.get(s, "#4C78A8") for s in status.index]),
        _bar_chart(pd.Series(filament_per_storey), "Filament je Geschoss", "Filament (g, Schätzung)", horizontal=True),
        _histogram_thicknesses(printed),
    )
    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:
        for fig in figures:
            pdf.savefig(fig)
            plt.close(fig)
    return buffer.getvalue()
