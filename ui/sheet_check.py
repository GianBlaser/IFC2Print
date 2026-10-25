"""Blatt 05 «Prüfen» (Variante «Übersicht»): Prüfpunkte der Analyse und Berichte.

Zweck:   Drei Kacheln nach Schwere (fehlen im Druck, geerbte Regel, Hinweise), der wichtigste nächste Schritt als Karte
         «ALS NÄCHSTES» mit Aktion, die übrigen Prüfpunkte als Klappzeilen (Erklärung, Einträge, Aktion), die
         Kategorien ohne Befund und die Downloads CSV, Prüfbericht und PDF-Report.
Eingabe: die Seite (page) mit Sitzung (check_points, Ergebnis) und dem Blatt «Ausgabe» für die Downloads
Ausgabe: das Blatt 05 (Element self.sheet); content.refresh() zeichnet es neu
"""

from pathlib import Path

from nicegui import ui

from ui.texts import CHECK_CATEGORIES, EMPTY_SHEET_TEXT, STALE_NOTE
from ui.widgets import button, popup, sheet_frame, tag

# Schwere je Art des Prüfpunkts (alles andere: «info»)
SEVERITY = {"keine": "err", "geometry": "err", "geerbt": "warn", "ausreisser": "warn", "aggregate": "info"}


def severity(point: dict) -> str:
    return SEVERITY.get(point["kind"], "info")


def point_count(point: dict) -> int:
    """Anzahl eines Prüfpunkts: Summe der Einträge; Einträge ohne Zahl zählen einfach."""
    return sum(1 if n is None else n for _, n in point["entries"])


class SheetCheck:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.open_rows: set[int] = set()              # aufgeklappte Prüfpunkte (Index in check_points)
        with sheet_frame("Prüfen", "sheet-pruefen") as self.sheet:
            with ui.element("div").classes("pruef-body duenn"):
                self.content()

    @ui.refreshable_method
    def content(self) -> None:
        if self.s.df is None:
            tag("p", EMPTY_SHEET_TEXT, "hint")
            return
        points = self.s.check_points
        if not points:
            tag("div", "✓ Keine Auffälligkeiten.", "pruef-leer")
        self._tiles(points)
        following = next((p for p in points if p["target"]), None)
        if following is not None:
            self._next(following)
        for i, p in enumerate(points):
            if p is not following:
                self._fold(i, p)
        found = {p["category"] for p in points}
        quiet = [title for category, title in CHECK_CATEGORIES if category not in found]
        if quiet:
            tag("p", "Ohne Befund: " + " · ".join(quiet), "ohne-befund")
        self._downloads()

    def _tiles(self, points: list[dict]) -> None:
        """Kacheln nach Schwere, nicht klickbar."""
        err = sum(point_count(p) for p in points if severity(p) == "err")
        warn = sum(point_count(p) for p in points if severity(p) == "warn")
        info = sum(1 for p in points if severity(p) == "info")
        with ui.element("div").classes("kacheln"):
            for number, text, css_class in ((err, "Bauteile fehlen im Druck", "err"),
                                            (warn, "Bauteile mit geerbter Regel", "warn"), (info, "Hinweise", "info")):
                with ui.element("div").classes(f"kachel {css_class}"):
                    tag("b", str(number))
                    tag("span", text)

    def _next(self, p: dict) -> None:
        """Karte «ALS NÄCHSTES»: der erste Prüfpunkt mit Ziel, Rahmen in der Schwerefarbe, Aktion als Knopf."""
        with ui.element("div").classes(f"zustand {severity(p)}"):
            tag("small", "ALS NÄCHSTES")
            tag("b", f"{p['title']} · {point_count(p)}")
            tag("p", p["explanation"])
            self._action(p, "naechstes")

    def _fold(self, i: int, p: dict) -> None:
        """Klappzeile eines Prüfpunkts; aufgeklappt Erklärung, Einträge als Chips und die Aktion als Textknopf."""
        is_open = i in self.open_rows
        with ui.element("div").classes(f"klapp {severity(p)}"):
            with ui.element("button").on("click", lambda: self._toggle(i)):
                tag("i")
                tag("span", p["title"])
                tag("small", str(point_count(p)) if p["entries"] else "")
                tag("em", "▾" if is_open else "▸")
            if not is_open:
                return
            with ui.element("div").classes("klapp-inhalt"):
                tag("p", p["explanation"])
                if p["entries"]:
                    with ui.element("div").classes("pruef-chips"):
                        for text, n in p["entries"]:
                            with ui.element("span").classes("pruef-chip"):
                                tag("span", text)
                                if n is not None:
                                    tag("b", f"{n}×")
                                popup(text)
                self._action(p, "textknopf")

    def _action(self, p: dict, css_class: str) -> None:
        """«Regeln anlegen →» (Ziel 03) bzw. «Im Modell zeigen →» (Geometrie, Ausreisser)."""
        if p["target"] == "regeln":
            button(css_class, self._create_rules, text="Regeln anlegen →")
        elif p["kind"] in ("geometry", "ausreisser"):
            button(css_class, lambda: self._show_in_model(p["kind"]), text="Im Modell zeigen →")

    def _toggle(self, i: int) -> None:
        self.open_rows ^= {i}
        self.content.refresh()

    def _downloads(self) -> None:
        """CSV und Prüfbericht immer; der PDF-Report mit Druckteil braucht ein (aktuelles) Ergebnis."""
        download = self.page.sheet_output.download
        base_name = Path(self.s.filename).stem
        with ui.element("div").classes("pruef-downloads"):
            button("", lambda: download(self.s.csv, f"{base_name}_bauteile.csv"), text="CSV Bauteile")
            button("", lambda: download(self.s.check_report_pdf, f"{base_name}_pruefbericht.pdf"),
                   text="Prüfbericht PDF")
            if self.s.result is not None:
                with button("", lambda: download(self.s.report_pdf, f"{base_name}_report.pdf",
                                                 from_result=True), text="PDF-Report") as b:
                    if self.s.stale:
                        popup(STALE_NOTE)
                if self.s.stale:
                    b.props("disabled")

    def _create_rules(self) -> None:
        self.page.go_to("regeln", keep_open=True)
        self.page.sheet_rules.select_tab("klassen")

    async def _show_in_model(self, kind: str) -> None:
        """Betroffene Bauteile im Viewer hervorheben (Ansicht IFC)."""
        df = self.s.df
        guids = list(df.loc[df["geometry"] != "ok" if kind == "geometry" else df["category"] == "Ausreisser", "guid"])
        self.page.panel.set_mode("ifc")
        await self.page.sheet_elements.set_selection(guids)
