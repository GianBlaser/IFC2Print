"""Report: Übergabeblatt als PDF (Jinja2-Template, gesetzt mit WeasyPrint) und CSV der Bauteiltabelle.

Eingabe: ``ReportData`` (core/output/report_data.py) bzw. Bauteiltabelle
Ausgabe: PDF- bzw. CSV-Datei als Bytes

WeasyPrint braucht Pango. Unter Windows kommt es aus MSYS2 (README, Abschnitt PDF-Report); ist der Ordner
PANGO_DLL_DIR vorhanden, wird er ohne weitere Einstellung gefunden.
"""

import base64
import os
import sys
from pathlib import Path

import jinja2
import pandas as pd
from markupsafe import Markup

from config import PANGO_DLL_DIR
from core.output.report_data import ReportData

TEMPLATES = Path(__file__).parent / "templates"


class ReportUnavailable(RuntimeError):
    """WeasyPrint oder Pango fehlt – der PDF-Report lässt sich nicht setzen."""


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
    """Bauteiltabelle als UTF-8-CSV mit BOM (öffnet in Excel korrekt), Kopfzeile deutsch (CSV_HEADERS).

    Ohne ``reason``: die Begründung steht je Regel im PDF-Anhang, nicht tausendfach je Bauteil.
    """
    return df.drop(columns="reason", errors="ignore").rename(columns=CSV_HEADERS).to_csv(index=False).encode("utf-8-sig")


def report_pdf(data: ReportData) -> bytes:
    """Übergabeblatt als PDF: Übergabe mit Urteil, Regelwerk mit Prüfpunkten, Anhang mit allen Bauteilen."""
    weasyprint = _weasyprint()
    environment = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATES), autoescape=True,
                                     trim_blocks=True, lstrip_blocks=True)
    image = base64.b64encode(data.image_png).decode("ascii") if data.image_png else None
    band = _css_string(f"{data.head['projekt']} · {data.head['massstab']}")      # Kopfband ab Seite 2
    html = environment.get_template("report.html.j2").render(d=data, image=image, band=band)
    return weasyprint.HTML(string=html, base_url=str(TEMPLATES)).write_pdf()


def _css_string(text: str) -> Markup:
    """Text als CSS-Zeichenkette für ``content`` im <style> des Templates (Anführungszeichen und «<» maskiert)."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("<", "\\3C ").replace("\n", " ")
    return Markup(f'"{escaped}"')


def available() -> bool:
    """True, wenn WeasyPrint samt Pango geladen werden kann (Tests, Skripte)."""
    try:
        _weasyprint()
    except ReportUnavailable:
        return False
    return True


def _weasyprint():
    """WeasyPrint erst beim ersten Report laden; fehlt es (oder Pango), eine verständliche Meldung."""
    if sys.platform == "win32" and Path(PANGO_DLL_DIR).is_dir():
        os.environ.setdefault("WEASYPRINT_DLL_DIRECTORIES", PANGO_DLL_DIR)
    try:
        import weasyprint
    except (ImportError, OSError) as error:
        raise ReportUnavailable("PDF-Report braucht WeasyPrint – siehe README") from error
    return weasyprint
