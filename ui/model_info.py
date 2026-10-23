"""Modell-Info im Panel: das Modell im Druckbett.

Zweck:   Zeigt X/Y/Z des Modells im Massstab mit Auslastung des Bauraums (passt, knapp, zu gross), bei knapp oder
         zu gross einen Vorschlag (kleinerer Massstab, mehrere Teile), die reale Gebäudegrösse und den Sprung zu 05.
Eingabe: die Seite (page) mit Sitzung und Modell-Übersicht (page.overview aus core.pipeline.model_overview)
Ausgabe: der Block «Modell im Druckbett» im Panel; content.refresh() zeichnet ihn neu
"""

from nicegui import ui

from ui.texts import BED_AXES, FIT_MARK, FIT_NOTE, TIGHT_THRESHOLD
from ui.widgets import button, mm_text, tag


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
        if u is None:
            return
        with ui.element("section").classes("panel-modell"):
            if u["dimensions_m"] is None:
                tag("p", "Keine Geometrie auswertbar.", "hint")
            else:
                self._print_bed(u)
            self._footer(u)

    def _print_bed(self, u: dict) -> None:
        """Kopf mit Urteil, eine Zeile je Achse und – bei knapp oder zu gross – der Vorschlag."""
        model, print_bed = u["model_mm"], u["bauraum_mm"]
        severity = fit_class(max(m / b for m, b in zip(model, print_bed)))
        with ui.element("div").classes("bett-kopf"):
            tag("h3", f"Modell 1:{u['scale']} im Druckbett")
            tag("span", FIT_MARK[severity], f"bett-marke {severity}")
        with ui.element("div").classes("bett"):
            for axis, mm, bed_mm in zip(BED_AXES, model, print_bed):
                self._axis(axis, mm, bed_mm)
        if severity != "ok":
            self._suggestion(u)

    def _axis(self, axis: str, mm: float, bed_mm: float) -> None:
        """Eine Achse: Mass im Modell, Balken der Auslastung und Bauraum."""
        fraction = mm / bed_mm
        fit = fit_class(fraction)
        with ui.element("div").classes(f"bett-achse {fit}"):
            tag("span", axis, "bett-label")
            with tag("b", mm_text(mm)):
                tag("small", "mm")
            with ui.element("span").classes("bett-balken").props(f'title="{fraction:.0%} des Bauraums"'):
                tag("i").style(f"width: {min(100, fraction * 100):.0f}%")
            tag("small", f"von {bed_mm:.0f}" + FIT_NOTE[fit], "bett-von")

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
                tag("span", f"in {n} Teilen drucken", "vorschlag nur-hinweis").props(
                    'title="ZIP je Geschoss in der unteren Leiste"')

    def _footer(self, u: dict) -> None:
        """Fusszeile: Gebäude real und Sprung zu den Prüfpunkten (05)."""
        with ui.element("div").classes("panel-fuss"):
            if u["dimensions_m"] is not None:
                x, y, z = u["dimensions_m"]
                text = f"Gebäude real {x:.1f} × {y:.1f} × {z:.1f} m"
                tag("span", text, "bett-real").props(f'title="{text}"')
            if self.s.check_points:
                button("panel-link", lambda: self.page.go_to("pruefen", keep_open=True),
                       text=f"{len(self.s.check_points)} ⚠ → 05")
