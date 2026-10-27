"""Die Seite: Einstieg und Koordinator der Oberfläche.

Zweck:   Baut die Seite aus ihren Teilen auf – Leiste links, Kopfzeile (Setup | Matrix), Blätter 01, 03–05 und Verlauf,
         Detail-Karte, Ansichtsleiste rechts, untere Leiste – und koordiniert sie: Blatt öffnen, Geschoss wählen,
         Meldung zeigen, Theme wechseln, Analyse neu anzeigen. Jedes Blatt steckt in einer eigenen Datei (sheet_*.py)
         und spricht die anderen über die Seite (page) an.
         Reine Darstellung und Bedienung; jede Fachlogik läuft über ui.state → core.pipeline.
         Das Aussehen steckt vollständig in ui/theme.css (Design «Planwerk»).
Eingabe: eine Sitzung (ui.state.Session); app.py ruft Page(Session(...)), page.viewer und page.load_start_model
Ausgabe: die aufgebaute Seite im Browser; Änderungen laufen über setting(), select_storey(), show_analysis() und die Blätter
"""

from nicegui import app, run, ui

from ui import start_model
from ui.bottom_bar import BottomBar
from ui.detail import Detail
from ui.header import Header
from ui.panel import Panel
from ui.rail import Rail
from ui.sheet_check import SheetCheck
from ui.sheet_file import SheetFile
from ui.sheet_history import SheetHistory
from ui.sheet_output import SheetOutput
from ui.sheet_rules import SheetRules
from ui.state import Session
from ui.texts import FONTS, THEME_CSS, WIDTH_03
from ui.viewer import Viewer
from ui.widgets import button, remember, saved, set_class, tag


class Page:
    def __init__(self, session: Session):
        self.s = session
        self.client = ui.context.client   # zum Prüfen, ob die Seite nach Verbindungsabbruch noch lebt
        self.overview: dict | None = None      # Modell-Info (core.pipeline.model_overview)
        self.floor_sel: str | None = None      # in der Matrix gewähltes Geschoss (filtert Viewer und 03)
        self.open_sheet = ""                   # Name des offenen Blattes («» = keines)
        ui.add_head_html(FONTS)
        ui.add_css(THEME_CSS)
        ui.query("body").props(f"data-theme={self.s.theme}")
        with ui.element("div").classes("app kopf-matrix") as self.root:
            self.viewer = Viewer(self.on_viewer_click)
            with ui.element("div").classes("laden hidden") as self.loading:
                with ui.element("div").classes("laden-punkte"):
                    for _ in range(3):
                        tag("i")
                self.loading_text = tag("span")
            with ui.element("div").classes("status") as self.message:
                self.message_text = tag("span")
                button("status-zu", self.hide_message, text="×").props('aria-label="Meldung schliessen"').mark(
                    "meldung-zu")
            self.message.set_visibility(False)
            self._message_count = 0               # zählt Meldungen (der 4-s-Zeitgeber gilt nur der eigenen)
            self.rail = Rail(self)
            self.header = Header(self)
            self._build_sheets()
            self.detail = Detail(self)
            self.panel = Panel(self)
            self.bottom_bar = BottomBar(self)
            with ui.element("footer").classes("unten-leiste") as self.bottom_bar.frame:
                self.bottom_bar.content()
        self._widths_03()
        self.header.show_mode()
        chapter = saved("kapitel", "datei")
        self.go_to(chapter if chapter in self.sheets or chapter == "" else "datei", keep_open=True)

    def _build_sheets(self) -> None:
        """Die Blätter liegen übereinander; go_to() zeigt höchstens eines davon."""
        with ui.element("div").classes("sheets"):
            self.sheet_file = SheetFile(self)
            self.sheet_rules = SheetRules(self)
            self.sheet_elements = self.sheet_rules.elements      # Tab «Bauteile» im Blatt 03
            self.sheet_output = SheetOutput(self)
            self.sheet_check = SheetCheck(self)
            self.sheet_history = SheetHistory(self)
        self.sheets = {"datei": self.sheet_file.sheet, "regeln": self.sheet_rules.sheet,
                       "ausgabe": self.sheet_output.sheet, "pruefen": self.sheet_check.sheet,
                       "verlauf": self.sheet_history.sheet}

    def _widths_03(self) -> None:
        """Gemerkte Breiten von 03 (je Tab) an .app setzen; der Griff meldet neue Breiten zurück."""
        for tab, (start, low, high) in WIDTH_03.items():
            key = f"breite_03_{tab}"
            self.root.style(f"--breite-03-{tab}: {min(high, max(low, int(saved(key, start))))}px")
            ui.on(key, lambda e, k=key, t=tab: self._width_reported(k, t, int(e.args)))

    def _width_reported(self, key: str, tab: str, width: int) -> None:
        remember(key, width)
        self.root.style(f"--breite-03-{tab}: {width}px")     # Server-Stand = Browser-Stand (sonst setzt ein Update zurück)

    # --- Koordination: Blätter, Geschoss, Meldungen, Theme ---------------------------------------

    def go_to(self, name: str, keep_open: bool = False) -> None:
        """Blatt öffnen; ein Klick auf das bereits offene Blatt schliesst es (mehr Platz für den Viewer).
        ``keep_open``: Sprung aus einem anderen Element – ein offenes Blatt bleibt offen.
        «setup» ist kein Blatt: 02 schaltet die Kopfzeile zwischen Setup und Matrix um."""
        if name == "setup":
            self.header.toggle_mode()
            return
        if not keep_open and name in self.sheets and "active" in self.sheets[name].classes:
            name = ""
        for n, sheet in self.sheets.items():
            set_class(sheet, "active", n == name)
        self.open_sheet = name
        self.rail.set_active(name)
        remember("kapitel", name)
        self.detail.show()
        self.panel.show_legend()

    async def select_storey(self, name: str | None) -> None:
        """Geschoss in der Matrix wählen (derselbe Klick nochmals = aufheben): Viewer abdunkeln und umranden,
        beide Tabs von 03 filtern. Die Bauteil-Auswahl wird dabei aufgehoben."""
        self.floor_sel = None if name == self.floor_sel else name
        self.viewer.select_storey(self.floor_sel)
        await self.sheet_elements.set_selection([])
        if not self.is_alive():
            return
        self.sheet_elements.fill_table()
        self.sheet_rules.show_filter()
        self.sheet_rules.rule_list.refresh()
        self.header.content.refresh()

    def is_alive(self) -> bool:
        """False, sobald die Seite (der Client) gelöscht ist – nach Verbindungsabbruch/Reload.
        Hintergrund-Tasks (run.io_bound) laufen weiter; ohne diese Prüfung crasht der erste
        UI-Zugriff danach mit 'The parent element this slot belongs to has been deleted.'"""
        return not self.client.is_deleted

    def show_message(self, text: str, kind: str = "info") -> None:
        """Meldung mittig unter der Kopfzeile; Art «info», «ok» (verschwindet nach 4 s), «warn» oder «err».
        Jede Meldung lässt sich mit × schliessen."""
        if not self.is_alive():
            return
        self._message_count += 1
        self.message_text.set_text(text)
        self.message.classes(replace=f"status {kind}")
        self.message.set_visibility(True)
        if kind == "ok":
            count = self._message_count       # eine neuere Meldung bleibt stehen
            # fester Elternknoten: der auslösende Knopf kann nach einem Neuzeichnen schon gelöscht sein
            with self.root:
                ui.timer(4, lambda: count == self._message_count and self.hide_message(), once=True)

    def hide_message(self) -> None:
        if self.is_alive():
            self.message.set_visibility(False)

    def show_loading(self, filename: str | None) -> None:
        """Ladeanzeige in der Mitte des Viewers («IFC wird geladen · Datei»); None blendet sie aus."""
        if not self.is_alive():
            return
        self.loading_text.set_text(f"IFC wird geladen · {filename}" if filename else "")
        set_class(self.loading, "hidden", filename is None)

    def theme_switch(self) -> None:
        self.s.theme = "dark" if self.s.theme == "light" else "light"
        app.storage.user["theme"] = self.s.theme
        ui.query("body").props(f"data-theme={self.s.theme}")
        self.rail.show_theme()
        self.viewer.theme(self.s.theme)

    async def on_viewer_click(self, hits: list, multi_select: bool) -> None:
        """Klick im Modell: das Blatt «Bauteile» bestimmt das getroffene Bauteil und wählt es."""
        await self.sheet_elements.viewer_click(hits, multi_select)

    # --- Modell laden und Analyse anzeigen ------------------------------------------------------

    async def load_start_model(self) -> None:
        """Beim Öffnen der Seite das Beispielmodell zeigen – voll nutzbar wie ein Upload."""
        if self.s.ifc is None:
            self.show_loading(start_model.file_path().name)
        try:
            ifc = await start_model.fetch()
            if ifc is None or self.s.ifc is not None:       # kein Beispiel oder Nutzer war schneller
                return
            await run.io_bound(self.s.load_model, ifc, start_model.file_path().name)
            if not self.is_alive():
                return
            self.sheet_file.set_label(f"Beispiel: {self.s.filename}")
            await self.show_model()
        finally:
            self.show_loading(None)

    async def show_model(self) -> None:
        """Nach dem Laden einer Datei: Modell, Tabellen und Blätter zeigen."""
        if not self.is_alive():
            return
        self.floor_sel = None                                # neues Modell: keine Geschoss-Auswahl
        self.sheet_file.show_remove_button()
        await self.show_analysis(camera=True)
        if self.is_alive():
            self.panel.set_mode("ifc")

    def clear_analysis(self) -> None:
        """Leerer Startzustand: alles, was von der Analyse abhängt, leeren und neu zeichnen."""
        self.overview = None
        self.floor_sel = None
        self.viewer.building_elements({}, {}, {})
        self.sheet_elements.clear()
        for part in (self.header.content, self.bottom_bar.content, self.sheet_output.content, self.sheet_check.content,
                     self.sheet_rules.rule_list, self.detail.content, self.sheet_file.model_info.content):
            part.refresh()
        self.sheet_rules.show_filter()
        self.detail.show()
        self.rail.mark()
        self.panel.set_mode("ifc")

    async def show_analysis(self, camera: bool = False) -> None:
        """Alles, was von der Analyse abhängt, neu zeichnen (Viewer, Kopfzeile, Tabelle, Modellkarte, Blätter)."""
        if self.s.df is None:
            return
        ifc_glb, status_glb, self.overview = await run.io_bound(self.s.preview)
        if not self.is_alive():
            return
        if self.floor_sel not in {g["name"] for g in self.overview["storeys"]}:
            self.floor_sel = None
        self.viewer.selected_storey = self.floor_sel
        self.viewer.building_elements(ifc_glb, status_glb, {g["name"]: g["color"] for g in self.overview["storeys"]})
        if camera:
            center, size, height = self.s.frame()
            p = self.s.profile_data
            self.viewer.frame(center, size, height, (p["build_volume_x_mm"], p["build_volume_y_mm"]), self.s.theme)
        self.header.content.refresh()
        self.sheet_file.model_info.content.refresh()
        self.sheet_elements.fill_table()
        self.refresh_result_views()
        self.sheet_rules.show_filter()
        self.sheet_rules.rule_list.refresh()         # Klassen ohne eigene Regel hängen vom Modell ab
        self.panel.show_legend()
        existing = set(self.s.df["guid"])
        selected = self.sheet_elements.selection_guids
        await self.sheet_elements.set_selection([g for g in selected if g in existing])   # Hervorhebung neu aufbauen

    def refresh_result_views(self) -> None:
        """Blatt 04, untere Leiste, Prüfliste und Leiste links neu zeichnen (Ergebnis oder Veraltet hat sich geändert)."""
        self.sheet_output.content.refresh()
        self.bottom_bar.content.refresh()
        self.sheet_check.content.refresh()
        self.rail.mark()

    async def setting(self, field_name: str, value) -> None:
        """Einstellung ändern → Ergebnis gilt als veraltet (Downloads gesperrt); Felder, die die
        Analyse betreffen, analysieren sofort neu, die übrigen wirken erst beim Erzeugen."""
        new = await run.io_bound(self.s.apply_setting, field_name, value)
        if not self.is_alive():
            return
        if self.s.ifc is not None:
            if new:
                geometry = field_name in ("scale", "profile", "align")
                if geometry:
                    self.viewer.stl({})               # alte STL-Vorschau liegt nicht mehr am Modell
                await self.show_analysis(camera=geometry)
            else:
                self.refresh_result_views()
        if not self.is_alive():
            return
        if field_name == "scale" and self.s.ifc is None:   # mit Modell zeichnet show_analysis sie neu
            self.sheet_rules.rule_list.refresh()
        if field_name == "scale":
            self.sheet_rules.parameter_list.refresh()
        self.header.show_alignment()   # Qualität, Öffnungen, Steckverbinder je Massstab; Ausrichtwinkel
