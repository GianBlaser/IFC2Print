"""Blatt 04 «Ausgabe»: Modell erzeugen, Fortschritt zeigen und Dateien herunterladen.

Zweck:   «STL erzeugen» startet die Erzeugung im Hintergrund, zeigt den Fortschritt und lässt das Gebäude im Viewer
         aufbauen. Danach stehen Urteil und Warnungen im Blatt, Kennzahlen und Downloads in der unteren Leiste.
Eingabe: die Seite (page) mit Sitzung (Ergebnis, Veraltet-Zustand, laufende Erzeugung), Viewer und Panel
Ausgabe: das Blatt 04 (Element self.sheet); content.refresh() zeichnet es neu; download() schickt Dateien an den Browser
"""

from collections.abc import Callable

from nicegui import run, ui

from core.pipeline import Result
from ui.texts import EMPTY_SHEET_TEXT
from ui.widgets import button, set_class, sheet_frame, tag


class SheetOutput:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        with sheet_frame("Ausgabe", "04 / 05", "sheet-modell") as self.sheet:
            with ui.element("div").classes("sheet-body"):
                self.content()

    @ui.refreshable_method
    def content(self) -> None:
        if self.s.df is None:
            tag("p", EMPTY_SHEET_TEXT, "hint leer")
            return
        ifc_classes = sorted(self.s.df.loc[self.s.df["is_printed"], "ifc_class"].unique())
        tag("p", "Gedruckte IFC-Klassen: " + (", ".join(ifc_classes) or "–"), "hint")
        if self.s.check_points:
            button("pruef-link", lambda: self.page.go_to("pruefen"),
                   text=f"{len(self.s.check_points)} Prüfpunkte ansehen → 05")
        if self.s.stale:
            tag("div", "⚠ Veraltet – Einstellungen geändert, neu erzeugen. Downloads sind bis dahin gesperrt.",
                "veraltet-text")
        self.generate_button = button("btn btn-primary btn-block", self.generate,
                                      text="Erneut erzeugen" if self.s.result else "STL erzeugen")
        if not ifc_classes or self.s.running:
            self.generate_button.props("disabled")
        self._progress_bar()
        if self.s.result:
            self._show_result()

    def _progress_bar(self) -> None:
        with ui.element("div").classes("fortschritt" + ("" if self.s.running else " hidden")) as self.progress:
            with ui.element("div").classes("fortschritt-kopf"):
                self.progress_text = tag("span", "")
                self.progress_pct = tag("span", "0%")
            with ui.element("div").classes("fortschritt-balken"):
                self.progress_bar = tag("i")

    def _show_result(self) -> None:
        """04: Urteil und Warnungen; Kennzahlen und Downloads stehen in der unteren Leiste."""
        e = self.s.result
        if e.watertight:
            tag("div", "✓ Wasserdichtes Modell erzeugt.", "ok-zeile")
        for w in e.warnings:
            tag("p", w, "hint")
        tag("p", f"{e.metrics['Verdickt']} Bauteile verdickt · {e.metrics['Gefüllt']} gefüllt · "
                 f"{len(e.parts)} Geschoss-Teile", "hint")

    # --- Erzeugen ------------------------------------------------------------------------------

    async def generate(self) -> None:
        """Modell erzeugen, Fortschritt zeigen und das Ergebnis im Viewer anzeigen."""
        if self.s.running:          # Doppelklick oder neu gerenderter Knopf: nur EIN Lauf je Sitzung
            return
        self._start_run()
        with self.progress:   # eigener, stabiler Elternknoten (nicht der gesperrte Knopf)
            timer = ui.timer(0.25, self._show_progress)
        try:
            result = await run.io_bound(self.s.generate)
            if result is None:                         # während des Laufs etwas geändert: Ergebnis verworfen
                self.page.show_message("Einstellungen haben sich während der Erzeugung geändert – Ergebnis "
                                       "verworfen, bitte neu erzeugen.", "warn")
                return
            await self._show_in_viewer(result)
        except Exception as error:
            self.page.show_message(f"Fehler: {error}", "err")
        finally:
            self._finish_run(timer)

    def _start_run(self) -> None:
        """Lauf beginnen: Knopf sperren, Fortschritt zeigen, Viewer in den Aufbau-Modus."""
        page = self.page
        self.s.running = True
        self.generate_button.props("disabled")
        set_class(self.progress, "hidden", False)
        page.panel.set_mode("status")                  # Gebäude baut sich im Status-Modus auf
        if page.viewer.exploded:
            page.panel.toggle_exploded()
        self.s.progress = ("Start", 0.0)
        page.viewer.build_up(0.0)

    async def _show_in_viewer(self, result: Result) -> None:
        """Erzeugtes Modell im STL-Modus zeigen und das Urteil melden."""
        page = self.page
        glb = await run.io_bound(lambda: result.preview)
        if not page.is_alive():
            return
        page.viewer.stl(glb)
        page.viewer.build_up(None)
        page.panel.set_mode("stl")
        if "active" in self.sheet.classes:
            page.go_to("ausgabe")                      # 04 schliessen: Ergebnis steht in Viewer und unterer Leiste
        page.show_message("Wasserdichtes Modell erzeugt." if result.watertight
                          else "Modell erzeugt, aber nicht wasserdicht – im Slicer prüfen.",
                          "ok" if result.watertight else "warn")

    def _finish_run(self, timer) -> None:
        """Lauf beenden (auch nach Fehler): Zeitgeber stoppen, Ansichten und Verlauf neu zeichnen."""
        page = self.page
        self.s.running = False
        timer.cancel()
        if page.is_alive():
            page.viewer.build_up(None)
            page.refresh_result_views()
            page.sheet_history.content.refresh()

    def _show_progress(self) -> None:
        phase, fraction = self.s.progress
        self.progress_text.set_text(phase)
        self.progress_pct.set_text(f"{fraction:.0%}")
        self.progress_bar.style(f"width: {fraction * 100:.0f}%")
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
        ui.download(data, filename)
        page.show_message(f"{filename} bereit.", "ok")
