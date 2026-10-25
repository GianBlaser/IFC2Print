"""Untere Leiste: Ausgabeziel FDM, kommende Ziele, Kennzahlen und Downloads.

Zweck:   Links steht das aktive Ziel FDM, daneben senkrecht «BALD» mit Lasercut und 3MF Farbe. Rechts davon je nach
         Zustand ein Hinweis (kein Modell, noch nicht erzeugt), der Fortschritt der Erzeugung oder Filament, Druckzeit
         und Kosten (Herleitung beim Darüberfahren) mit den Downloads «Gebäude», «Geschosse» und «Platziert».
Eingabe: die Seite (page) mit Sitzung (Ergebnis, Veraltet-Zustand, Fortschritt) und dem Blatt «Ausgabe» für Erzeugen und
         Download
Ausgabe: der Inhalt von <footer class="unten-leiste"> (page setzt ``frame``); content.refresh() zeichnet ihn neu
"""

from collections.abc import Callable
from pathlib import Path

from nicegui import ui

from config import OUTPUT_TARGETS
from core.output import estimate
from core.pipeline import Result
from ui.texts import DOWNLOADS, STALE_NOTE
from ui.widgets import button, popup, set_class, tag


class BottomBar:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.frame: ui.element | None = None          # <footer>, angelegt von ui/page.py
        self.progress_views: list = []                # (Phase, Prozent, Balken, Vortext) der laufenden Erzeugung

    @ui.refreshable_method
    def content(self) -> None:
        s = self.s
        if self.frame is not None:
            set_class(self.frame, "veraltet", s.stale)
        self.progress_views = []
        self._targets()
        if s.ifc is None:
            self._hint("Zuerst IFC laden →", "link", lambda: self.page.go_to("datei", keep_open=True), "01 Datei")
        elif s.running:
            self._progress()
        elif s.result is None:
            self._hint("Noch nicht erzeugt", "fdm-erzeugen", self.generate, f"{s.output_target.name} erzeugen")
        else:
            self._figures(s.result)
            if s.stale:
                with ui.element("button").classes("veraltet-feld").on("click", self.generate):
                    tag("span", "⚠ Veraltet")
                    tag("span", "neu erzeugen")
            tag("div", "", "strich hell")
            self._downloads(s.result)

    def _targets(self) -> None:
        """Aktives Ziel (FDM) gross, dann «BALD» senkrecht und die noch nicht umgesetzten Ziele übereinander."""
        active = self.s.output_target
        with ui.element("div").classes("ziel-fdm"):
            tag("b", active.name)
            tag("small", active.format)
            popup(active.description_text)
        tag("div", "", "strich")
        with ui.element("div").classes("bald"):
            tag("span", "BALD")
        with ui.element("div").classes("stapel-knoepfe"):
            for z in OUTPUT_TARGETS:
                if not z.available:
                    with tag("span", z.name, "ziel-bald"):
                        popup(z.description_text)
        tag("div", "", "strich hell")

    def _hint(self, text: str, css_classes: str, on_click: Callable, button_text: str) -> None:
        """Hinweis mit Knopf (kein Modell geladen oder noch nichts erzeugt)."""
        with ui.element("div").classes("unten-hinweis"):
            tag("span", text)
            button(css_classes, on_click, text=button_text)

    def _progress(self) -> None:
        """Fortschritt über die Restbreite: «Ziel · Massstab · Qualität · Phase» und Prozent, Balken darunter."""
        s = self.s
        prefix = f"{s.output_target.name} · {s.scale} · {s.quality} · "
        phase, fraction = s.progress
        with ui.element("div").classes("unten-fortschritt"):
            with ui.element("div").classes("fortschritt-kopf"):
                text = tag("span", prefix + phase)
                pct = tag("span", f"{fraction * 100:.0f} %")
            with ui.element("div").classes("fortschritt-balken"):
                bar = tag("i").style(f"width: {fraction * 100:.0f}%")
        self.progress_views = [(text, pct, bar, prefix)]

    def _figures(self, e: Result) -> None:
        """Filament, Druckzeit und Kosten; beim Darüberfahren erscheint die Herleitung."""
        derivation = estimate.derivation(e.volume_cm3, e.height_mm, e.layer_height_mm, e.density_g_cm3,
                                         e.price_chf_kg)
        for label, value in (("Filament", f"{e.grams:.0f} g" if e.grams >= 100 else f"{e.grams:.1f} g"),
                             ("Druckzeit", f"{e.time_h:.1f} h"), ("Kosten", f"CHF {e.cost_chf:.2f}")):
            with ui.element("div").classes("kennzahl"):
                tag("b", value)
                tag("span", f"{label} ⓘ")
                with popup():
                    tag("b", label)
                    for row in derivation[label][0]:
                        tag("div", row)
                    tag("div", "Schätzung – Faktoren in config.py, kein Slicer-Ergebnis.", "schaetzung")

    def _downloads(self, e: Result) -> None:
        """«Gebäude» gross, «Geschosse» und «Platziert» übereinander; bei veraltetem Ergebnis gesperrt."""
        download = self.page.sheet_output.download
        base_name = Path(self.s.filename).stem
        files = {
            "stl": ("gebaeude", e.stl, f"{base_name}.stl"),
            "zip": ("download-klein", lambda: e.stl_zip(base_name), f"{base_name}_geschosse.zip"),
            "plate": ("download-klein", lambda: e.stl_plate(self.s.profile_data), f"{base_name}_platte.stl"),
        }
        exports = [k for k in self.s.output_target.exports if k in files]
        for key in exports[:1]:
            self._download_button(key, *files[key], download)
        if exports[1:]:
            tag("div", "", "strich")
            with ui.element("div").classes("stapel-knoepfe"):
                for key in exports[1:]:
                    self._download_button(key, *files[key], download)

    def _download_button(self, key: str, css_class: str, bytes_factory: Callable, name: str, download: Callable) -> None:
        text, tip = DOWNLOADS[key]
        with button(css_class, lambda: download(bytes_factory, name, from_result=True), text=text).mark(
                f"download-{key}") as b:
            popup(tip + (f"\n{STALE_NOTE}" if self.s.stale else ""))
        if self.s.stale:
            b.props("disabled")

    async def generate(self) -> None:
        """Erzeugen aus der Leiste; der Fortschritt läuft hier und in Blatt 04."""
        await self.page.sheet_output.generate()
