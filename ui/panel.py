"""Ansicht rechts: Panel «Geschosse · Modell», Griff zum Auf- und Zuklappen und senkrechte Ansichtsleiste.

Zweck:   Das Panel zeigt die Matrix (Geschoss × Status) und das Modell im Druckbett; die Leiste schaltet den Viewer
         zwischen IFC, STAT (Druckbarkeit) und STL um und zieht die Geschosse auseinander.
Eingabe: die Seite (page) mit Sitzung, Viewer und Modell-Übersicht (page.overview)
Ausgabe: <div class="ansicht"> rechts mit der Legende der Status-Ansicht; content.refresh() zeichnet das Panel neu
"""

from nicegui import ui

from ui.matrix import Matrix
from ui.model_info import ModelInfo
from ui.texts import ARROW_SVG, EXPLODE_SVG, LEGEND, VIEW_MODES
from ui.widgets import button, remember, saved, set_class, tag


class Panel:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.matrix = Matrix(page)
        self.model_info = ModelInfo(page)
        self.is_open = bool(saved("panel_offen", True))
        with ui.element("div").classes("ansicht" + (" offen" if self.is_open else "")) as self.view_box:
            with ui.element("aside").classes("ansicht-panel"):
                self.content()
            self._tools()
        with ui.element("div").classes("legende hidden") as self.legend:
            for css_class, text in LEGEND:
                tag("span", text, f"leg {css_class}")
        self._mark_view_tabs("ifc")

    def _tools(self) -> None:
        """Dunkler Griff (auf/zu) und senkrechte Leiste IFC · STAT · STL · ⇕."""
        with ui.element("div").classes("ansicht-werkzeug"):
            with ui.element("button").classes("ansicht-griff").on("click", self._toggle).props(
                    f'title="{"Panel zuklappen" if self.is_open else "Panel aufklappen"}"') as self.handle:
                ui.html(ARROW_SVG, sanitize=False)
            with ui.element("div").classes("ansicht-leiste"):
                self.view_tabs = {m: button("", lambda m=m: self.set_mode(m), text=text).props(f'title="{title}"')
                                  .mark(f"ansicht-{m}") for m, text, title in VIEW_MODES}
                tag("span", "", "ansicht-trenner")
                with ui.element("button").classes("explode").on("click", self.toggle_exploded).props(
                        'title="Geschosse auseinander"') as self.explode_switch:
                    ui.html(EXPLODE_SVG, sanitize=False)

    def _toggle(self) -> None:
        self.is_open = not self.is_open
        set_class(self.view_box, "offen", self.is_open)
        self.handle.props(f'title="{"Panel zuklappen" if self.is_open else "Panel aufklappen"}"')
        remember("panel_offen", self.is_open)

    @ui.refreshable_method
    def content(self) -> None:
        with ui.element("div").classes("panel-kopf"):
            tag("span", "Geschosse · Modell")
            tag("small", self.s.ifc.schema if self.s.ifc is not None else "")
        if self.s.ifc is None or self.page.overview is None:
            with ui.element("p").classes("panel-leer"):
                tag("span", "Zuerst IFC laden → ")
                button("", lambda: self.page.go_to("datei", keep_open=True), text="01 Datei")
            return
        self.matrix.content()
        self.model_info.content()

    def set_mode(self, mode: str) -> None:
        """Ansicht des Viewers wählen: «ifc», «status» oder «stl»; die Legende gehört nur zu «status»."""
        self.page.viewer.set_mode(mode)
        self._mark_view_tabs(mode)
        display = mode == "status" and self.s.df is not None
        set_class(self.legend, "hidden", not display)

    def _mark_view_tabs(self, mode: str) -> None:
        for m, b in self.view_tabs.items():
            set_class(b, "active", m == mode)

    def toggle_exploded(self) -> None:
        """Geschosse auseinander ziehen oder wieder zusammenschieben."""
        enabled = not self.page.viewer.exploded
        self.page.viewer.set_exploded(enabled)
        set_class(self.explode_switch, "active", enabled)
