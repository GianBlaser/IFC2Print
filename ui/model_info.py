"""Modellkarte in Blatt 01: das Modell im Druckbett.

Zweck:   Zeigt Projektname, Datei und Schema, das Urteil in der Ecke (passt, knapp, zu gross), die Isometrie von Bauraum
         und Modell mit Massen (ui/bed_iso.py), die Kennzahlen Bauteile, Geschosse und reale Grösse und – bei knapp oder
         zu gross – einen Vorschlag (kleinerer Massstab, mehrere Teile).
Eingabe: die Seite (page) mit Sitzung und Modell-Übersicht (page.overview aus core.pipeline.model_overview)
Ausgabe: die Modellkarte im Blatt 01; content.refresh() zeichnet sie neu
"""

from nicegui import ui

from core.output.model_info import bed_fit
from ui.bed_iso import COLORS, bed_iso_svg
from ui.texts import FIT_MARK, TIGHT_THRESHOLD
from ui.widgets import button, popup, tag


def fit_class(fraction: float) -> str:
    """Anteil am Bauraum → «ok», «knapp» (über 90 %) oder «gross» (über 100 %)."""
    return "ok" if fraction <= TIGHT_THRESHOLD else "knapp" if fraction <= 1 else "gross"


class ModelInfo:
    def __init__(self, page):
        self.page = page
        self.s = page.s

    @ui.refreshable_method
    def content(self) -> None:
        u = self.page.overview
        if u is None or self.s.ifc is None:
            return
        if u["dimensions_m"] is None:
            tag("p", "Keine Geometrie auswertbar.", "hint")
            return
        model, print_bed = u["model_mm"], u["bauraum_mm"]
        fraction, rotated = bed_fit(model, print_bed)
        severity = fit_class(fraction)
        if rotated:                                  # quer aufs Bett: gezeichnet wird die Lage, die passt
            model = [model[1], model[0], model[2]]
        _, side, _, line = COLORS[severity]
        with ui.element("div").classes("modellkarte"):
            tag("span", FIT_MARK[severity], f"urteil {severity}")
            with ui.element("div").classes("modell-kopf"):
                tag("b", self.s.project_name() or self.s.filename)
                tag("small", f"{self.s.filename} · {self.s.ifc.schema}")
            ui.html(bed_iso_svg(tuple(print_bed), tuple(model), severity), sanitize=False).classes("iso")
            with ui.element("div").classes("modell-legende"):
                with tag("span"):
                    tag("i", "", "bauraum")
                    tag("span", f"Bauraum {self.s.profile}")
                with tag("span"):
                    tag("i").style(f"background: {side}; border: 1px solid {line}")
                    tag("span", f"Modell {self.s.scale}" + (" · 90° gedreht" if rotated else ""))
            x, y, z = u["dimensions_m"]
            with ui.element("div").classes("modell-fakten"):
                for value, word in ((str(len(self.s.df)), "Bauteile"), (str(len(u["storeys"])), "Geschosse"),
                                    (f"{x:.1f} × {y:.1f} × {z:.1f}", "Real (m)")):
                    with ui.element("div"):
                        tag("b", value)
                        tag("small", word)
            if severity != "ok":
                self._suggestion(u)

    def _suggestion(self, u: dict) -> None:
        """Vorschlag: kleinerer Massstab, der passt, und der Hinweis auf mehrere Teile."""
        with ui.element("div").classes("vorschlag-box"):
            tag("b", "Vorschlag")
            if suggestion := self.s.scale_suggestion(u):
                name, height = suggestion
                button("vorschlag", lambda n=name: self.page.setting("scale", n),
                       text=f"{name} → {height:.0f} mm hoch")
            n = len(u["storeys"])
            if n > 1:
                with tag("span", f"in {n} Teilen drucken", "vorschlag nur-hinweis"):
                    popup("«Geschosse» in der unteren Leiste")
