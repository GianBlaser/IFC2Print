"""Blatt 05 «Prüfen»: Prüfpunkte der Analyse und Berichte.

Zweck:   Zeigt als Karten je Kategorie, was anders gedruckt wird als man erwarten könnte (Klassen ohne Regel,
         defekte Geometrie, Ausreisser, Umgebung …), mit der passenden Aktion, dazu Prüfbericht, CSV und PDF-Report.
Eingabe: die Seite (page) mit Sitzung (check_points, Ergebnis) und dem Blatt «Ausgabe» für die Downloads
Ausgabe: das Blatt 05 (Element self.sheet); content.refresh() zeichnet es neu
"""

from pathlib import Path

from nicegui import ui

from ui.texts import CHECK_CATEGORIES, EMPTY_SHEET_TEXT
from ui.widgets import button, sheet_frame, tag

# Farbe der Karte je Art des Prüfpunkts (alles andere: «info»)
SEVERITY = {"keine": "err", "geerbt": "warn", "ausreisser": "warn", "geometry": "err"}


class SheetCheck:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        with sheet_frame("Prüfen", "05 / 05", "sheet-wide") as self.sheet:
            with ui.element("div").classes("sheet-body pruef-body"):
                self.content()

    @ui.refreshable_method
    def content(self) -> None:
        if self.s.df is None:
            tag("p", EMPTY_SHEET_TEXT, "hint leer")
            return
        if not self.s.check_points:
            tag("div", "✓ Keine Auffälligkeiten.", "pruef-leer")
        self._checklist()

    def _checklist(self) -> None:
        """Prüfliste als Karten je Kategorie: was anders gedruckt wird als man erwarten könnte, mit Aktion."""
        with ui.element("div").classes("pruefliste" + ("" if self.s.check_points else " hidden")):
            for category, title in CHECK_CATEGORIES:
                points = [p for p in self.s.check_points if p["category"] == category]
                if not points:
                    continue
                with ui.element("div").classes("pruef-kopf"):
                    tag("b", title)
                    tag("small", str(len(points)))
                for p in points:
                    self._card(p)
        self._downloads()

    def _card(self, p: dict) -> None:
        """Eine Karte (aufklappbar): Titel mit Zahl, Erklärung, Einträge und Aktionen."""
        with ui.element("details").classes(f"pruef-karte {SEVERITY.get(p['kind'], 'info')}"):
            with ui.element("summary"):
                tag("i")
                tag("span", p["title"])
                if p["entries"]:
                    tag("small", str(sum(n or 1 for _, n in p["entries"])))
            tag("p", p["explanation"], "hint")
            if p["entries"]:
                with ui.element("div").classes("pruef-chips"):
                    for text, n in p["entries"]:
                        with ui.element("span").classes("pruef-chip").props(f'title="{text}"'):
                            tag("span", text)
                            if n is not None:
                                tag("b", f"{n}×")
            with ui.element("div").classes("pruef-aktionen"):
                if p["target"] == "regeln":
                    button("pruef-link", self._create_rules, text="Regeln anlegen →")
                if p["kind"] in ("geometry", "ausreisser"):
                    button("pruef-link", lambda a=p["kind"]: self._show_in_model(a), text="Im Modell zeigen →")

    def _downloads(self) -> None:
        """Prüfbericht und CSV immer; der PDF-Report mit Druckteil braucht ein Ergebnis."""
        download = self.page.sheet_output.download
        base_name = Path(self.s.filename).stem
        with ui.element("div").classes("downloads"):
            button("btn btn-ghost", lambda: download(self.s.check_report_pdf, f"{base_name}_pruefbericht.pdf"),
                   text="Prüfbericht PDF")
            button("btn btn-ghost", lambda: download(self.s.csv, f"{base_name}_bauteile.csv"), text="CSV Bauteile")
            if self.s.result is not None:
                e = self.s.result
                b = button("btn btn-ghost", lambda: download(lambda: e.report_pdf(self.s.df), f"{base_name}_report.pdf",
                                                             from_result=True), text="PDF-Report")
                if self.s.stale:
                    b.props('disabled title="Veraltet – zuerst neu erzeugen"')

    def _create_rules(self) -> None:
        self.page.go_to("regeln", keep_open=True)
        self.page.sheet_rules.select_tab("klassen")

    async def _show_in_model(self, kind: str) -> None:
        """Betroffene Bauteile im Viewer hervorheben (Ansicht IFC)."""
        df = self.s.df
        guids = list(df.loc[df["geometry"] != "ok" if kind == "geometry" else df["category"] == "Ausreisser", "guid"])
        self.page.panel.set_mode("ifc")
        await self.page.sheet_elements.set_selection(guids)
