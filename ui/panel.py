"""Ansicht rechts: schmale Ansichtsleiste und Legende der Status-Ansicht im Viewer.

Zweck:   Die Leiste schaltet den Viewer zwischen IFC, STAT (Druckbarkeit) und STL um und zieht die Geschosse
         auseinander. Die Legende steht rechts neben dem offenen Blatt, aber nur im Modus Setup der Kopfzeile –
         im Modus Matrix steht sie in der Kopfzeile.
Eingabe: die Seite (page) mit Sitzung, Viewer, Kopfzeile (Modus) und offenem Blatt
Ausgabe: <div class="ansicht"> rechts und <div class="legende"> über dem Viewer
"""

from nicegui import ui

from ui.texts import EXPLODE_SVG, LEGEND, SHEET_WIDTH, VIEW_MODES
from ui.widgets import button, popup, set_class, tag


class Panel:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        with ui.element("div").classes("ansicht"):
            self.view_tabs = {}
            for m, text, title in VIEW_MODES:
                with button("", lambda m=m: self.set_mode(m), text=text).mark(f"ansicht-{m}") as b:
                    popup(title)
                self.view_tabs[m] = b
            tag("span", "", "ansicht-trenner")
            with ui.element("button").classes("explode").on("click", self.toggle_exploded) as self.explode_switch:
                ui.html(EXPLODE_SVG, sanitize=False)
                popup("Geschosse auseinander")
        with ui.element("div").classes("legende hidden") as self.legend:
            for css_class, _, text in LEGEND:
                tag("span", text, f"leg {css_class}")
        self._mark_view_tabs("ifc")

    def set_mode(self, mode: str) -> None:
        """Ansicht des Viewers wählen: «ifc», «status» oder «stl»."""
        self.page.viewer.set_mode(mode)
        self._mark_view_tabs(mode)
        self.show_legend()

    def show_legend(self) -> None:
        """Legende nur im Modus Setup und solange der Viewer die Druckbarkeit zeigt (STAT, oder STL ohne Ergebnis);
        sie steht 16 px rechts neben dem offenen Blatt."""
        viewer = self.page.viewer
        display = self.page.header.mode == "setup" and self.s.df is not None and viewer.shows_status
        set_class(self.legend, "hidden", not display)
        sheet = self.page.open_sheet
        if sheet == "regeln" and self.page.sheet_rules.tab == "bauteile":
            sheet = "regeln-bauteile"
        width = SHEET_WIDTH.get(sheet)
        self.legend.style(f"left: calc(var(--content-x) + {width} + 16px)" if width else "left: var(--content-x)")

    def _mark_view_tabs(self, mode: str) -> None:
        for m, b in self.view_tabs.items():
            set_class(b, "active", m == mode)

    def toggle_exploded(self) -> None:
        """Geschosse auseinander ziehen oder wieder zusammenschieben."""
        enabled = not self.page.viewer.exploded
        self.page.viewer.set_exploded(enabled)
        set_class(self.explode_switch, "active", enabled)
