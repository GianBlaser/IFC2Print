"""Blatt 03 «Regeln», Tab «Bauteile»: Tabelle aller Bauteile, Filter, Auswahl und Ausnahmen.

Zweck:   Zeigt die Bauteile mit Status und Dicke, filtert nach Geschoss und Status (Klick in der Matrix) und hält die
         Auswahl von Tabelle und Viewer gleich. Gewählte Bauteile lassen sich drucken, nicht drucken oder wieder
         nach Regel behandeln; ein einzelnes Bauteil erscheint im Detailfeld (detail.py).
Eingabe: die Seite (page) mit Sitzung, Viewer und Blattwechsel; Klicks in Tabelle, Matrix und Viewer
Ausgabe: der Tab (Element self.tab) im Blatt 03; Ausnahmen werden gespeichert und das Modell neu analysiert
"""

import math

import pandas as pd
from nicegui import events, run, ui

from ui.detail import Detail
from ui.texts import COLUMNS, EXCEPTION_BUTTONS, NO_SELECTION_TEXT, PRINT_SLOT, STATUS_SHORT, STATUS_SLOT
from ui.widgets import button, set_class, tag


def table_row(z) -> dict:
    """Eine Tabellenzeile aus einer Zeile (itertuples) der Bauteiltabelle."""
    return {
        "guid": z.guid, "storey": z.storey, "category": z.category, "ifc_class": z.ifc_class, "name": z.name,
        "thickness": None if math.isnan(z.thickness_model_mm) else round(z.thickness_model_mm, 2),
        "package": None if math.isnan(z.package_thickness_mm) else round(z.package_thickness_mm),
        "is_printed": bool(z.is_printed), "status": z.status if z.is_printed else "nicht_gedruckt",
        "action": z.action, "geometry": z.geometry,
    }


class SheetElements:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.filter_status: str | None = None
        self.filter_storey: str | None = None
        self.only_printed_filter = False
        self.selection: dict | None = None         # Zeile des einzelnen gewählten Bauteils (Detail)
        self.selection_guids: list[str] = []       # alle gewählten Bauteile (Tabelle und Viewer)
        with ui.element("div").classes("tab-inhalt bauteile-tab") as self.tab:
            self._toolbar()
            self._table()
            self.detail = Detail(page, self)

    def _toolbar(self) -> None:
        """Filter-Chip, Schalter «nur zu druckende», Auswahltext und Sammelknöpfe."""
        with ui.element("div").classes("bauteile-kopf"):
            with ui.element("button").classes("chip hidden").on("click", self._clear_filter) as self.filter_chip:
                self.filter_text = tag("span")
            ui.checkbox("nur zu druckende", on_change=self._only_printed).props("dense size=xs").classes("check")
            self.selection_info = tag("span", NO_SELECTION_TEXT, "hint")
            with ui.element("div").classes("sammel hidden") as self.bulk:
                for action, text in EXCEPTION_BUTTONS:
                    button("", lambda a=action: self.selection_action(a), text=text)
                button("", lambda: self.set_selection([]), text="aufheben")

    def _table(self) -> None:
        self.table = ui.table(rows=[], columns=COLUMNS, row_key="guid", pagination=0, selection="multiple",
                              on_select=lambda e: self.set_selection([r["guid"] for r in e.selection])
                              ).props("flat dense virtual-scroll hide-bottom").classes("tabelle bauteile")
        self.table.add_slot("body-cell-status", STATUS_SLOT)
        self.table.add_slot("body-cell-is_printed", PRINT_SLOT)
        self.table.on("toggle_print", lambda e: self.set_exceptions([e.args[0]], "behalten" if e.args[1] else "entfernen"))
        self.table.on("rowClick", self._row_clicked, args=[["ctrlKey", "metaKey", "shiftKey"], None])

    def clear(self) -> None:
        """Ohne Modell: Auswahl und Tabelle leeren."""
        self.selection_guids, self.selection = [], None
        self.table.rows = []
        self.table.update()

    # --- Filter und Tabelle ---------------------------------------------------------------

    def show_elements(self, status: str | None = None, storey: str | None = None) -> None:
        """Blatt 03 › Bauteile mit diesem Filter öffnen (Klick auf Matrix, Geometrie-Zeile, Viewer)."""
        self.filter_status, self.filter_storey = status, storey
        self.page.go_to("regeln", keep_open=True)
        self.page.sheet_rules.select_tab("bauteile")
        self.fill_table()

    def _clear_filter(self) -> None:
        self.filter_status = self.filter_storey = None
        self.fill_table()

    def _only_printed(self, e: events.ValueChangeEventArguments) -> None:
        self.only_printed_filter = e.value
        self.fill_table()

    def _filtered(self, status: str | None, storey: str | None) -> pd.DataFrame:
        """Bauteile nach dem Filter aus der Matrix (Status, «geometry», «nicht_gedruckt») und Geschoss."""
        df = self.s.df
        if status == "geometry":
            df = df[df["geometry"] != "ok"]
        elif status == "nicht_gedruckt":
            df = df[~df["is_printed"]]
        elif status:
            df = df[df["is_printed"] & (df["status"] == status)]
        if storey:
            df = df[df["storey"] == storey]
        return df

    def fill_table(self) -> None:
        """Tabelle nach Filter neu füllen; Auswahl und Filter-Chip nachführen."""
        if self.s.df is None:
            return
        df = self._filtered(self.filter_status, self.filter_storey)
        if self.only_printed_filter:
            df = df[df["is_printed"]]
        self.table.rows = [table_row(z) for z in df.itertuples()]
        chosen = set(self.selection_guids)
        self.table.selected = [r for r in self.table.rows if r["guid"] in chosen]
        self.table.update()
        status_text = STATUS_SHORT.get(self.filter_status, self.filter_status)
        filter_text = " · ".join(f for f in (self.filter_storey, status_text) if f)
        self.filter_text.set_text(f"{filter_text} ×")
        set_class(self.filter_chip, "hidden", not filter_text)

    # --- Auswahl: Tabelle ↔ Viewer ---------------------------------------------------------

    async def _row_clicked(self, e: events.GenericEventArguments) -> None:
        """Klick = nur dieses Bauteil wählen (nochmals = abwählen) und die Kamera darauf richten;
        Strg/Cmd/Shift-Klick ergänzt die Auswahl."""
        modifier, guid = e.args[0], e.args[1]["guid"]
        multi_select = any(modifier.get(k) for k in ("ctrlKey", "metaKey", "shiftKey"))
        await self._toggle_selection(guid, multi_select)
        if not multi_select and self.selection_guids == [guid] and self.page.is_alive():
            box = await run.io_bound(self.s.element_box, guid)
            if box is not None and self.page.is_alive():
                self.page.viewer.display(*box)

    async def _toggle_selection(self, guid: str, multi_select: bool) -> None:
        if multi_select:
            guids = ([g for g in self.selection_guids if g != guid] if guid in self.selection_guids
                     else self.selection_guids + [guid])
        else:
            guids = [] if self.selection_guids == [guid] else [guid]
        await self.set_selection(guids)

    async def set_selection(self, guids: list[str]) -> None:
        """Gewählte Bauteile übernehmen: Tabelle, Detail, Sammelleiste und Hervorhebung im Viewer."""
        self.selection_guids = list(dict.fromkeys(guids))
        self._selection_ui()
        glb = await run.io_bound(self.s.selection_preview, self.selection_guids) if self.selection_guids else {}
        if self.page.is_alive():
            viewer = self.page.viewer
            if viewer.only_selection:                 # eigene Auswahl beendet das «nur diese zeigen» der Matrix
                viewer.isolate(False)
                self.page.panel.matrix.content.refresh()
            viewer.highlight(glb)

    async def isolate(self, status: str | None = None, storey: str | None = None) -> None:
        """Im Viewer nur die Bauteile mit diesem Filter zeigen (Klick auf die Matrix)."""
        if self.s.df is None:
            return
        guids = list(self._filtered(status, storey)["guid"])
        glb = await run.io_bound(self.s.selection_preview, guids) if guids else {}
        if self.page.is_alive():
            self.page.viewer.highlight(glb)
            self.page.viewer.isolate(True)

    async def show_all(self) -> None:
        """Wieder alle Bauteile zeigen; die Auswahl der Tabelle bleibt hervorgehoben."""
        self.page.viewer.isolate(False)
        await self.set_selection(self.selection_guids)

    def _selection_ui(self) -> None:
        rows = {r["guid"]: r for r in self.table.rows}
        self.table.selected = [rows[g] for g in self.selection_guids if g in rows]
        self.table.update()
        n = len(self.selection_guids)
        self.selection = rows.get(self.selection_guids[0]) if n == 1 else None
        set_class(self.tab, "has-detail", bool(self.selection))
        self.selection_info.set_text(NO_SELECTION_TEXT if n == 0 else
                                     "1 Bauteil gewählt" if n == 1 else f"{n} Bauteile gewählt")
        set_class(self.bulk, "hidden", not n)
        self.detail.content.refresh()

    def _guid_at(self, hits: list) -> str | None:
        """Bauteil an den Treffern des Viewers (nah → fern); läuft im Hintergrund-Thread."""
        for printed_only in (True, False):          # Geister (nicht gedruckt) nur, wenn nichts Gedrucktes getroffen ist
            for storey, point in hits:
                guid = self.s.element_at_point(storey, point, printed_only)
                if guid:
                    return guid
        return None

    async def viewer_click(self, hits: list, multi_select: bool) -> None:
        """Klick im Modell → Bauteil bestimmen, Tabelle öffnen und zur Zeile scrollen."""
        guid = await run.io_bound(self._guid_at, hits)
        if guid is None or not self.page.is_alive():
            return
        if guid not in {r["guid"] for r in self.table.rows}:      # Filter blendet das Bauteil aus
            self.filter_status = self.filter_storey = None
            self.fill_table()
        self.page.go_to("regeln", keep_open=True)
        self.page.sheet_rules.select_tab("bauteile")
        await self._toggle_selection(guid, multi_select)
        row = next((i for i, r in enumerate(self.table.rows) if r["guid"] == guid), None)
        if row is not None and guid in self.selection_guids:
            self.table.run_method("scrollTo", row)

    # --- Ausnahmen ---------------------------------------------------------------------------

    async def selection_action(self, action: str | None) -> None:
        await self.set_exceptions(list(self.selection_guids), action)

    async def set_exceptions(self, guids: list[str], action: str | None) -> None:
        """Bauteile drucken / nicht drucken (z.B. falsch erkannte Umgebung); None = wie Regel."""
        await run.io_bound(self.s.set_exceptions, guids, action)
        if not self.page.is_alive():
            return
        await self.page.show_analysis()

    async def set_exception(self, guid: str, action: str | None) -> None:
        await self.set_exceptions([guid], action)
