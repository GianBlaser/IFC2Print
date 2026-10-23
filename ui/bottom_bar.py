"""Untere Leiste: Ausgabeziele, Kennzahlen und Downloads.

Zweck:   Zeigt links die Ausgabeziele, in der Mitte Filament, Druckzeit und Kosten des Ergebnisses (mit Herleitung
         beim Darüberfahren) und rechts die Download-Knöpfe. Ohne Modell oder Ergebnis steht ein Hinweis.
Eingabe: die Seite (page) mit Sitzung (Ergebnis, Veraltet-Zustand) und dem Blatt «Ausgabe» für Erzeugen und Download
Ausgabe: der Inhalt von <footer class="unten-leiste">; content.refresh() zeichnet ihn neu
"""

from collections.abc import Callable
from pathlib import Path

from nicegui import ui

from config import OUTPUT_TARGETS
from core.output import estimate
from core.pipeline import Result
from ui.widgets import button, tag


class BottomBar:
    def __init__(self, page):
        self.page = page
        self.s = page.s

    @ui.refreshable_method
    def content(self) -> None:
        self._targets()
        with ui.element("div").classes("kennzahlen-zeile" + (" veraltet" if self.s.stale else "")):
            if self.s.ifc is None:
                self._hint("Zuerst IFC laden →", "", lambda: self.page.go_to("datei", keep_open=True), "01 Datei")
            elif self.s.result is None:
                self._hint("Noch nicht erzeugt", "btn btn-primary", self.generate,
                           f"{self.s.output_target.name} erzeugen")
            else:
                self._figures(self.s.result)
                self._downloads(self.s.result)

    def _targets(self) -> None:
        """Ausgabeziele (umgesetzt ist nur FDM); das gewählte ist hervorgehoben."""
        with ui.element("div").classes("ziele"):
            tag("span", "AUSGABEZIEL", "leiste-label")
            for z in OUTPUT_TARGETS:
                active = " aktiv" if z.key == self.s.target else ""
                with tag("span", "", "ziel" + active):
                    tag("b", z.name)
                    tag("small", z.format if z.available else "bald")
                    ui.tooltip(z.description_text).classes("tip")

    def _hint(self, text: str, css_classes: str, on_click: Callable, button_text: str) -> None:
        """Hinweis mit Knopf (kein Modell geladen oder noch nichts erzeugt)."""
        with ui.element("div").classes("unten-hinweis"):
            tag("span", text)
            button(css_classes, on_click, text=button_text)

    def _figures(self, e: Result) -> None:
        """Filament, Druckzeit und Kosten; beim Darüberfahren erscheint die Herleitung."""
        derivation = estimate.derivation(e.volume_cm3, e.height_mm, e.layer_height_mm, e.density_g_cm3,
                                         e.price_chf_kg)
        for label, value in (("Filament", f"{e.grams:.0f} g" if e.grams >= 100 else f"{e.grams:.1f} g"),
                             ("Druckzeit", f"{e.time_h:.1f} h"), ("Kosten", f"CHF {e.cost_chf:.2f}")):
            with ui.element("div").classes("kennzahl"):
                tag("b", value)
                tag("span", label)
                with ui.tooltip().classes("popup"):
                    tag("b", label)
                    for row in derivation[label][0]:
                        tag("div", row)
                    tag("div", "Schätzung – Faktoren in config.py, kein Slicer-Ergebnis.", "schaetzung")

    def _downloads(self, e: Result) -> None:
        """Download-Knöpfe des Ausgabeziels; bei veraltetem Ergebnis gesperrt."""
        download = self.page.sheet_output.download
        base_name = Path(self.s.filename).stem
        files = {
            "stl": ("btn btn-dark", "STL komplett", e.stl, f"{base_name}.stl"),
            "zip": ("btn btn-ghost", "ZIP je Geschoss", lambda: e.stl_zip(base_name), f"{base_name}_geschosse.zip"),
            "plate": ("btn btn-ghost", "Platte", lambda: e.stl_plate(self.s.profile_data), f"{base_name}_platte.stl"),
        }
        with ui.element("div").classes("downloads-block"):
            with ui.element("div").classes("downloads-kopf"):
                tag("span", f"DOWNLOADS · {self.s.output_target.name}", "leiste-label")
                if self.s.stale:
                    button("veraltet-hinweis", self.generate, text="⚠ Veraltet – neu erzeugen")
            with ui.element("div").classes("downloads"):
                for key in self.s.output_target.exports:
                    css_classes, text, bytes_factory, name = files[key]
                    b = button(css_classes, lambda f=bytes_factory, n=name: download(f, n, from_result=True), text=text)
                    if self.s.stale:
                        b.props('disabled title="Veraltet – zuerst neu erzeugen"')

    async def generate(self) -> None:
        """Erzeugen aus der Leiste: Blatt 04 öffnen (dort läuft der Fortschritt) und starten."""
        self.page.go_to("ausgabe", keep_open=True)
        await self.page.sheet_output.generate()
