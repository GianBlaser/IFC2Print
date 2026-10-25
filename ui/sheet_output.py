"""Blatt 04 «Ausgabe»: Modell erzeugen, Fortschritt zeigen und Dateien herunterladen.

Zweck:   Drei Kacheln (gedruckte Bauteile, Geschoss-Teile, Prüfpunkte), eine Statuskarte (bereit, läuft, erzeugt,
         veraltet) mit dem Knopf «STL erzeugen», danach die Ergebnis-Tabelle und aufklappbar die gedruckten IFC-Klassen
         und die Hinweise der Erzeugung. Die Erzeugung läuft im Hintergrund, das Gebäude baut sich im Viewer auf;
         Kennzahlen und Downloads stehen in der unteren Leiste. Das Blatt bleibt nach dem Erzeugen offen.
Eingabe: die Seite (page) mit Sitzung (Ergebnis, Veraltet-Zustand, laufende Erzeugung, Prüfpunkte), Viewer und Ansicht
Ausgabe: das Blatt 04 (Element self.sheet); content.refresh() zeichnet es neu; download() schickt Dateien an den Browser
"""

from collections.abc import Callable

import pandas as pd
from nicegui import run, ui

from core.pipeline import Result
from ui.texts import EMPTY_SHEET_TEXT
from ui.widgets import button, sheet_frame, tag

ERROR_KINDS = ("keine", "geometry")      # Prüfpunkte, bei denen Bauteile im Druck fehlen


class SheetOutput:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.open_rows: set[str] = set()                # aufgeklappte Klappzeilen
        self.result_settings = ("", "")                 # Massstab und Qualität des letzten Ergebnisses
        self.progress_views: list = []                  # (Phase, Prozent, Balken, Vortext) der laufenden Erzeugung
        with sheet_frame("Ausgabe", "sheet-ausgabe") as self.sheet:
            with ui.element("div").classes("ausgabe-body duenn"):
                self.content()

    @ui.refreshable_method
    def content(self) -> None:
        s = self.s
        if s.df is None:
            tag("p", EMPTY_SHEET_TEXT, "hint")
            return
        printed = s.df[s.df["is_printed"]]
        errors = [p for p in s.check_points if p["kind"] in ERROR_KINDS]
        parts = len(s.result.parts) if s.result is not None else printed["storey"].nunique()
        with ui.element("div").classes("kacheln"):
            self._tile(str(len(printed)), "Bauteile gedruckt", "ok", self.page.sheet_elements.show_printed)
            self._tile(str(parts), "Geschoss-Teile")
            self._tile(str(len(s.check_points)), "Prüfpunkte", "err" if errors else "info",
                       lambda: self.page.go_to("pruefen", keep_open=True))
        self._state_card(len(printed), parts, bool(errors))
        if s.result is not None:
            self._result_table(s.result)
        self._printed_classes(printed)
        if s.result is not None and s.result.warnings:
            self._warnings(s.result.warnings)

    def _tile(self, number: str, text: str, css_class: str = "", on_click: Callable | None = None) -> None:
        """Kachel «Fläche»: Zahl in der Kachelfarbe, darunter der Text; mit ``on_click`` ein Knopf."""
        with ui.element("button" if on_click else "div").classes(f"kachel {css_class}") as tile:
            tag("b", number)
            tag("span", text)
        if on_click:
            tile.on("click", on_click)

    def _state_card(self, n_printed: int, parts: int, errors: bool) -> None:
        """Statuskarte: genau einer der Zustände läuft, veraltet, erzeugt oder bereit – mit Knopf zum Erzeugen."""
        s = self.s
        if s.running:
            css, kicker, title, text = ("laeuft", "LÄUFT", "Modell wird erzeugt",
                                        "Das Gebäude baut sich im Viewer von unten nach oben auf.")
        elif s.stale:
            css, kicker, title, text = ("veraltet", "VERALTET", "Einstellungen geändert",
                                        "Das Ergebnis passt nicht mehr zu den Einstellungen. Downloads sind bis zum "
                                        "neuen Erzeugen gesperrt.")
        elif s.result is not None:
            css, kicker, title = "erzeugt", "ERZEUGT", f"{n_printed} Bauteile in {parts} Geschoss-Teilen"
            text = ("Wasserdichtes Modell erzeugt. Kennzahlen und Downloads stehen in der unteren Leiste."
                    if s.result.watertight else "Modell erzeugt, aber nicht wasserdicht – im Slicer prüfen.")
        else:
            css, kicker, title = "bereit", "BEREIT", f"{n_printed} Bauteile werden gedruckt"
            text = ("Einige Klassen haben keine Regel und fehlen im Druck – vorher in 05 prüfen." if errors
                    else "Alles bereit zum Erzeugen.")
        with ui.element("div").classes(f"zustand {css}"):
            tag("small", kicker)
            tag("b", title)
            tag("p", text)
            if s.running:
                self.progress_views = [self._progress_bar()]
            label = "Erzeuge …" if s.running else "Erneut erzeugen" if s.result is not None else "STL erzeugen"
            b = button("erzeugen" + (" laeuft" if s.running else ""), self.generate, text=label).mark("stl-erzeugen")
            if s.running or not n_printed:
                b.props("disabled")

    def _progress_bar(self) -> tuple:
        """Phase links, Prozent rechts, Balken darunter; Rückgabe: die drei Elemente zum Nachführen (ohne Vortext)."""
        phase, fraction = self.s.progress
        with ui.element("div").classes("fortschritt"):
            with ui.element("div").classes("fortschritt-kopf"):
                text = tag("span", phase)
                pct = tag("span", f"{fraction * 100:.0f} %")
            with ui.element("div").classes("fortschritt-balken"):
                bar = tag("i").style(f"width: {fraction * 100:.0f}%")
        return text, pct, bar, ""

    def _result_table(self, e: Result) -> None:
        scale, quality = self.result_settings
        with ui.element("div").classes("ergebnis"):
            for word, value in (("Massstab · Qualität", f"{scale or self.s.scale} · {quality or self.s.quality}"),
                                ("Verdickt · gefüllt", f"{e.metrics['Verdickt']} · {e.metrics['Gefüllt']}"),
                                ("Volumen", f"{e.volume_cm3:.1f} cm³"), ("Modellhöhe", f"{e.height_mm:.0f} mm")):
                with ui.element("div"):
                    tag("span", word)
                    tag("span", value)

    def _fold(self, key: str, title: str, count: int) -> bool:
        """Klappzeile: Punkt, Titel, Anzahl, Pfeil; True, wenn aufgeklappt (Inhalt folgt im with-Block des Aufrufers)."""
        is_open = key in self.open_rows
        with ui.element("button").on("click", lambda: self._toggle(key)):
            tag("i")
            tag("span", title)
            tag("small", str(count))
            tag("em", "▾" if is_open else "▸")
        return is_open

    def _toggle(self, key: str) -> None:
        self.open_rows ^= {key}
        self.content.refresh()

    def _printed_classes(self, printed: pd.DataFrame) -> None:
        counts = printed["ifc_class"].value_counts()
        with ui.element("div").classes("klapp ok"):
            if self._fold("klassen", "Gedruckte IFC-Klassen", len(counts)):
                with ui.element("div").classes("klapp-inhalt"):
                    with ui.element("div").classes("pruef-chips"):
                        for ifc_class, n in counts.items():
                            with ui.element("span").classes("pruef-chip"):
                                tag("span", ifc_class)
                                tag("b", f"{n}×")

    def _warnings(self, warnings: list[str]) -> None:
        with ui.element("div").classes("klapp warn"):
            if self._fold("hinweise", "Hinweise der Erzeugung", len(warnings)):
                with ui.element("div").classes("klapp-inhalt"):
                    for w in warnings:
                        tag("p", w)

    # --- Erzeugen ------------------------------------------------------------------------------

    async def generate(self) -> None:
        """Modell erzeugen, Fortschritt zeigen und das Ergebnis im Viewer anzeigen."""
        if self.s.running:          # Doppelklick oder neu gerenderter Knopf: nur EIN Lauf je Sitzung
            return
        settings = (self.s.scale, self.s.quality)
        self._start_run()
        with self.sheet:              # stabiler Elternknoten: überlebt das Neuzeichnen des Blattinhalts
            timer = ui.timer(0.25, self._show_progress)
        try:
            result = await run.io_bound(self.s.generate)
            if result is None:                         # während des Laufs etwas geändert: Ergebnis verworfen
                self.page.show_message("Einstellungen haben sich während der Erzeugung geändert – Ergebnis "
                                       "verworfen, bitte neu erzeugen.", "warn")
                return
            self.result_settings = settings
            await self._show_in_viewer(result)
        except Exception as error:
            self.page.show_message(f"Fehler: {error}", "err")
        finally:
            self._finish_run(timer)

    def _start_run(self) -> None:
        """Lauf beginnen: Knopf sperren, Fortschritt zeigen (Blatt und untere Leiste), Viewer in den Aufbau-Modus."""
        page = self.page
        self.s.running = True
        self.s.progress = ("Start", 0.0)
        page.panel.set_mode("status")                  # Gebäude baut sich im Status-Modus auf
        if page.viewer.exploded:
            page.panel.toggle_exploded()
        page.refresh_result_views()
        page.viewer.build_up(0.0)

    async def _show_in_viewer(self, result: Result) -> None:
        """Erzeugtes Modell im STL-Modus zeigen und das Urteil melden; das Blatt bleibt offen."""
        page = self.page
        glb = await run.io_bound(lambda: result.preview)
        if not page.is_alive():
            return
        page.viewer.stl(glb)
        page.viewer.build_up(None)
        page.panel.set_mode("stl")
        page.show_message("Wasserdichtes Modell erzeugt." if result.watertight
                          else "Modell erzeugt, aber nicht wasserdicht – im Slicer prüfen.",
                          "ok" if result.watertight else "warn")

    def _finish_run(self, timer) -> None:
        """Lauf beenden (auch nach Fehler): Zeitgeber stoppen, Ansichten und Verlauf neu zeichnen."""
        page = self.page
        self.s.running = False
        timer.cancel()
        self.progress_views = []
        if page.is_alive():
            page.viewer.build_up(None)
            page.refresh_result_views()
            page.sheet_history.content.refresh()

    def _show_progress(self) -> None:
        """Phase und Anteil in Blatt 04 und in der unteren Leiste nachführen, Viewer bis zu dieser Höhe zeigen."""
        phase, fraction = self.s.progress
        for text, pct, bar, prefix in self.progress_views + self.page.bottom_bar.progress_views:
            text.set_text(prefix + phase)
            pct.set_text(f"{fraction * 100:.0f} %")
            bar.style(f"width: {fraction * 100:.0f}%")
        self.page.viewer.build_up(fraction)

    # --- Download ------------------------------------------------------------------------------

    async def download(self, bytes_factory: Callable[[], bytes], filename: str, from_result: bool = False) -> None:
        """Datei im Hintergrund erzeugen und an den Browser schicken; ``from_result``: nie mit veralteten Daten."""
        page = self.page
        if from_result and self.s.stale:          # Sicherheit: nie mit veralteten Daten exportieren
            page.show_message("Ergebnis ist veraltet – bitte neu erzeugen.", "warn")
            return
        page.show_message(f"{filename} wird vorbereitet …")
        try:
            data = await run.io_bound(bytes_factory)
        except Exception as error:
            page.show_message(f"Fehler bei {filename}: {error}", "err")
            return
        if not page.is_alive():   # Verbindung während der Erzeugung weg → Download würde nie ankommen
            return
        with page.root:           # fester Kontext: der Download-Knopf ist nach einem Neuzeichnen evtl. gelöscht
            ui.download(data, filename)
        page.show_message(f"{filename} bereit.", "ok")
