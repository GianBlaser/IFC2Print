"""Die Seite: Einstieg und Koordinator der Oberfläche.

Zweck:   Baut die Seite aus ihren Teilen auf – Leiste links, Blätter 01–05 und Verlauf, Panel rechts, untere Leiste –
         und koordiniert sie: Blatt öffnen, Meldung zeigen, Theme wechseln, Analyse neu anzeigen. Jedes Blatt steckt
         in einer eigenen Datei (sheet_*.py) und spricht die anderen über die Seite (page) an.
         Reine Darstellung und Bedienung; jede Fachlogik läuft über ui.state → core.pipeline.
         Das Aussehen steckt vollständig in ui/theme.css (Design «Planwerk»).
Eingabe: eine Sitzung (ui.state.Session); app.py ruft Page(Session(...)), page.viewer und page.load_start_model
Ausgabe: die aufgebaute Seite im Browser; Änderungen laufen über setting(), show_analysis() und die Blätter
"""

from nicegui import app, run, ui

from ui import start_model
from ui.bottom_bar import BottomBar
from ui.panel import Panel
from ui.rail import Rail
from ui.sheet_check import SheetCheck
from ui.sheet_file import SheetFile
from ui.sheet_history import SheetHistory
from ui.sheet_output import SheetOutput
from ui.sheet_rules import SheetRules
from ui.sheet_setup import SheetSetup
from ui.state import Session
from ui.texts import FONTS, THEME_CSS
from ui.viewer import Viewer
from ui.widgets import remember, saved, set_class, tag


class Page:
    def __init__(self, session: Session):
        self.s = session
        self.client = ui.context.client   # zum Prüfen, ob die Seite nach Verbindungsabbruch noch lebt
        self.overview: dict | None = None      # Modell-Info (core.pipeline.model_overview)
        ui.add_head_html(FONTS)
        ui.add_css(THEME_CSS)
        ui.query("body").props(f"data-theme={self.s.theme}")
        with ui.element("div").classes("app"):
            self.viewer = Viewer(self.on_viewer_click)
            with ui.element("header").classes("title"):
                tag("h1", "IFC2Print")
                tag("p", "HSLU · Gian Blaser")
            self.message = tag("div", "", "status hidden")
            self.rail = Rail(self)
            self._build_sheets()
            self.panel = Panel(self)
            self.bottom_bar = BottomBar(self)
            with ui.element("footer").classes("unten-leiste"):
                self.bottom_bar.content()
        self.go_to(saved("kapitel", "datei"), keep_open=True)

    def _build_sheets(self) -> None:
        """Die Blätter liegen übereinander; go_to() zeigt höchstens eines davon."""
        with ui.element("div").classes("sheets"):
            self.sheet_file = SheetFile(self)
            self.sheet_setup = SheetSetup(self)
            self.sheet_rules = SheetRules(self)
            self.sheet_elements = self.sheet_rules.elements      # Tab «Bauteile» im Blatt 03
            self.sheet_output = SheetOutput(self)
            self.sheet_check = SheetCheck(self)
            self.sheet_history = SheetHistory(self)
        self.sheets = {"datei": self.sheet_file.sheet, "setup": self.sheet_setup.sheet,
                       "regeln": self.sheet_rules.sheet, "ausgabe": self.sheet_output.sheet,
                       "pruefen": self.sheet_check.sheet, "verlauf": self.sheet_history.sheet}

    # --- Koordination: Blätter, Meldungen, Theme ---------------------------------------------

    def go_to(self, name: str, keep_open: bool = False) -> None:
        """Blatt öffnen; ein Klick auf das bereits offene Blatt schliesst es (mehr Platz für den Viewer).
        ``keep_open``: Sprung aus einem anderen Element – ein offenes Blatt bleibt offen."""
        if not keep_open and name in self.sheets and "active" in self.sheets[name].classes:
            name = ""
        for n, sheet in self.sheets.items():
            set_class(sheet, "active", n == name)
        self.rail.set_active(name)
        remember("kapitel", name)

    def is_alive(self) -> bool:
        """False, sobald die Seite (der Client) gelöscht ist – nach Verbindungsabbruch/Reload.
        Hintergrund-Tasks (run.io_bound) laufen weiter; ohne diese Prüfung crasht der erste
        UI-Zugriff danach mit 'The parent element this slot belongs to has been deleted.'"""
        return not self.client.is_deleted

    def show_message(self, text: str, kind: str = "info") -> None:
        """Meldung oben in der Mitte; Art «info», «ok» (verschwindet nach 4 s), «warn» oder «err»."""
        if not self.is_alive():
            return
        self.message.set_text(text)
        self.message.classes(replace=f"status {kind}")
        if kind == "ok":
            ui.timer(4, lambda: set_class(self.message, "hidden", True), once=True)

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
        ifc = await start_model.fetch()
        if ifc is None or self.s.ifc is not None:       # kein Beispiel oder Nutzer war schneller
            return
        await run.io_bound(self.s.load_model, ifc, start_model.file_path().name)
        if not self.is_alive():
            return
        self.sheet_file.set_label(f"Beispiel: {self.s.filename} – eigene IFC-Datei hierher ziehen")
        await self.show_model()

    async def show_model(self) -> None:
        """Nach dem Laden einer Datei: Modell, Tabellen und Blätter zeigen."""
        if not self.is_alive():
            return
        self.sheet_file.show_remove_button()
        await self.show_analysis(camera=True)
        if self.is_alive():
            self.sheet_setup.content.refresh()           # Geschoss-Chips des neuen Modells (mit Farben)
        self.panel.set_mode("ifc")

    def clear_analysis(self) -> None:
        """Leerer Startzustand: alles, was von der Analyse abhängt, leeren und neu zeichnen."""
        self.overview = None
        self.viewer.building_elements({}, {}, {})
        self.sheet_elements.clear()
        for part in (self.panel.content, self.bottom_bar.content, self.sheet_output.content, self.sheet_check.content,
                     self.sheet_rules.rule_list, self.sheet_setup.content, self.sheet_elements.detail.content):
            part.refresh()
        self.rail.mark()
        self.panel.set_mode("ifc")

    async def show_analysis(self, camera: bool = False) -> None:
        """Alles, was von der Analyse abhängt, neu zeichnen (Viewer, Kacheln, Tabelle, Modell-Blatt)."""
        if self.s.df is None:
            return
        ifc_glb, status_glb, self.overview = await run.io_bound(self.s.preview)
        if not self.is_alive():
            return
        self.viewer.building_elements(ifc_glb, status_glb, {g["name"]: g["color"] for g in self.overview["storeys"]})
        if camera:                                       # neues Modell: gemerkte ausgeblendete Geschosse übernehmen
            names = {g["name"] for g in self.overview["storeys"]}
            self.viewer.hide(set(saved("versteckt", [])) & names)
        self.panel.content.refresh()
        if camera:
            center, size, height = self.s.frame()
            p = self.s.profile_data
            self.viewer.frame(center, size, height, (p["build_volume_x_mm"], p["build_volume_y_mm"]), self.s.theme)
        self.sheet_elements.fill_table()
        self.refresh_result_views()
        self.sheet_rules.rule_list.refresh()         # Klassen ohne eigene Regel hängen vom Modell ab
        self.sheet_setup.show_alignment()
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
        if field_name == "scale":
            self.sheet_setup.content.refresh()           # Qualität, Öffnungen, Steckverbinder je Massstab
            self.sheet_rules.show_scale()                # 02 und 03 synchron
            if self.s.ifc is None:                       # mit Modell zeichnet show_analysis sie neu
                self.sheet_rules.rule_list.refresh()
        self.sheet_setup.show_alignment()   # auch ohne geladene Datei (Schalterzustand)
