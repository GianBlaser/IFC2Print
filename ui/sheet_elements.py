"""Blatt 03 «Regeln», Tab «Bauteile»: Tabelle aller Bauteile, Suche, Auswahl und Ausnahmen.

Zweck:   Zeigt die Bauteile nach IFC-Klasse gruppiert (grösste Gruppe zuerst) mit Klasse, Geschoss, Dicke, Status und
         Regel, gefiltert auf das in der Matrix gewählte Geschoss, die Suche und «nur zu druckende». Die Auswahl von
         Tabelle und Viewer bleibt gleich; ein einzelnes Bauteil erscheint in der Detail-Karte (detail.py) und mit
         einem Etikett im Viewer. Gewählte Bauteile lassen sich drucken, nicht drucken oder wieder nach Regel behandeln.
Eingabe: die Seite (page) mit Sitzung, Viewer, Geschoss-Auswahl (page.floor_sel) und Blattwechsel; Klicks in Tabelle
         und Viewer
Ausgabe: der Tab (Element self.tab) im Blatt 03; Ausnahmen werden gespeichert und das Modell neu analysiert
"""

import math

from nicegui import events, run, ui

from ui.texts import BODY_SLOT, COLUMNS, EXCEPTION_BUTTONS, NO_SELECTION_TEXT, ROW_CLICK_JS, STATUS_CLASS_NAME
from ui.widgets import button, set_class, tag


def table_row(z, exceptions: dict[str, str] | None = None) -> dict:
    """Eine Tabellenzeile aus einer Zeile (itertuples) der Bauteiltabelle; ``exceptions``: GUID → Aktion."""
    exception = z.guid in (exceptions or {})
    return {
        "guid": z.guid, "storey": z.storey, "category": z.category, "ifc_class": z.ifc_class,
        "name": z.name or z.ifc_class,
        "thickness": None if math.isnan(z.thickness_model_mm) else round(z.thickness_model_mm, 2),
        "is_printed": bool(z.is_printed), "status": z.status if z.is_printed else "nicht_gedruckt",
        "action": z.action, "geometry": z.geometry,
        "rule": "Ausnahme" if exception else z.action, "is_exception": exception,
        "group_head": "", "group_count": 0,
    }


def grouped_by_class(rows: list[dict]) -> list[dict]:
    """Zeilen nach IFC-Klasse gruppiert (grösste Gruppe zuerst, darin in Tabellenreihenfolge);
    die erste Zeile jeder Gruppe trägt den Gruppenkopf «Klasse» mit Anzahl."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["ifc_class"], []).append(r)
    result = []
    for ifc_class, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        members[0]["group_head"], members[0]["group_count"] = ifc_class, len(members)
        result += members
    return result


class SheetElements:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.search_text = ""
        self.only_printed_filter = False
        self.selection: dict | None = None         # Zeile des einzelnen gewählten Bauteils (Detail)
        self.selection_guids: list[str] = []       # alle gewählten Bauteile (Tabelle und Viewer)
        with ui.element("div").classes("tab-inhalt bauteile-tab") as self.tab:
            self._toolbar()
            self._table()
            self.no_selection = tag("div", NO_SELECTION_TEXT, "kein-detail")

    def _toolbar(self) -> None:
        """Suche, Kästchen «nur zu druckende», Anzahl und – ab zwei gewählten Bauteilen – die Sammelknöpfe."""
        with ui.element("div").classes("bauteile-kopf"):
            self.search_input = ui.input(placeholder="Bauteil suchen", on_change=self._search).props(
                "dense outlined clearable debounce=150").classes("suchfeld")
            with ui.element("button").classes("nur-druck").on("click", self._toggle_only_printed) as self.only_printed_box:
                tag("i")
                tag("span", "nur zu druckende")
            self.count_text = tag("span", "", "anzahl")
            with ui.element("div").classes("sammel hidden") as self.bulk:
                for action, text in EXCEPTION_BUTTONS:
                    button("", lambda a=action: self.selection_action(a), text=text)
                button("", lambda: self.set_selection([]), text="aufheben")

    def _table(self) -> None:
        self.table = ui.table(rows=[], columns=COLUMNS, row_key="guid", pagination=0, selection="multiple",
                              on_select=lambda e: self.set_selection([r["guid"] for r in e.selection])
                              ).props("flat dense virtual-scroll hide-bottom").classes("tabelle bauteile duenn")
        self.table.add_slot("header-selection", "")
        self.table.add_slot("body", BODY_SLOT)
        self.table.on("click", self._row_clicked, js_handler=ROW_CLICK_JS)

    def clear(self) -> None:
        """Ohne Modell: Auswahl und Tabelle leeren."""
        self.selection_guids, self.selection = [], None
        self.table.rows = []
        self.table.update()
        self.count_text.set_text("")
        self.page.viewer.label(None)

    # --- Filter und Tabelle ---------------------------------------------------------------

    def show_printed(self) -> None:
        """Blatt 03 › Bauteile mit «nur zu druckende» öffnen (Kachel «Bauteile gedruckt» in 04)."""
        self.only_printed_filter = True
        set_class(self.only_printed_box, "an", True)
        self.page.go_to("regeln", keep_open=True)
        self.page.sheet_rules.select_tab("bauteile")
        self.fill_table()

    def _search(self, e: events.ValueChangeEventArguments) -> None:
        self.search_text = (e.value or "").strip().lower()
        self.fill_table()

    def _toggle_only_printed(self) -> None:
        self.only_printed_filter = not self.only_printed_filter
        set_class(self.only_printed_box, "an", self.only_printed_filter)
        self.fill_table()

    def fill_table(self) -> None:
        """Tabelle nach Geschoss, Suche und «nur zu druckende» neu füllen; Auswahl und Anzahl nachführen."""
        if self.s.df is None:
            return
        df = self.s.df
        if self.page.floor_sel:
            df = df[df["storey"] == self.page.floor_sel]
        if self.search_text:
            df = df[df["name"].fillna("").str.lower().str.contains(self.search_text, regex=False)
                    | df["ifc_class"].str.lower().str.contains(self.search_text, regex=False)]
        if self.only_printed_filter:
            df = df[df["is_printed"]]
        self.table.rows = grouped_by_class([table_row(z, self.s.exceptions) for z in df.itertuples()])
        chosen = set(self.selection_guids)
        self.table.selected = [r for r in self.table.rows if r["guid"] in chosen]
        self.table.update()
        self.count_text.set_text(f"{len(self.table.rows)} Bauteile")
        self.page.sheet_rules.show_filter()

    # --- Auswahl: Tabelle ↔ Viewer ---------------------------------------------------------

    async def _row_clicked(self, e: events.GenericEventArguments) -> None:
        """Klick = nur dieses Bauteil wählen (nochmals = abwählen) und die Kamera darauf richten;
        Strg/Cmd/Shift-Klick ergänzt die Auswahl."""
        guid, multi_select = e.args["guid"], bool(e.args["multi"])
        await self._toggle_selection(guid, multi_select)
        if not multi_select and self.selection_guids == [guid] and self.page.is_alive():
            box = await run.io_bound(self.s.element_box, guid)
            if box is not None and self.page.is_alive():
                row = self.s.df[self.s.df["guid"] == guid]
                self.page.viewer.display(*box, row.iloc[0].storey if not row.empty else "")

    async def _toggle_selection(self, guid: str, multi_select: bool) -> None:
        if multi_select:
            guids = ([g for g in self.selection_guids if g != guid] if guid in self.selection_guids
                     else self.selection_guids + [guid])
        else:
            guids = [] if self.selection_guids == [guid] else [guid]
        await self.set_selection(guids)

    async def set_selection(self, guids: list[str]) -> None:
        """Gewählte Bauteile übernehmen: Tabelle, Detail, Sammelknöpfe, Hervorhebung und Etikett im Viewer."""
        self.selection_guids = list(dict.fromkeys(guids))
        self._selection_ui()
        glb = await run.io_bound(self.s.selection_preview, self.selection_guids) if self.selection_guids else {}
        single = self.selection_guids[0] if len(self.selection_guids) == 1 else None
        box = await run.io_bound(self.s.element_box, single) if single else None
        if self.page.is_alive():
            self.page.viewer.highlight(glb)
            self._show_label(single, box)

    def _show_label(self, guid: str | None, box: tuple | None) -> None:
        """Etikett «Name + Status» am einzeln gewählten Bauteil, sonst keines."""
        row = self.s.df[self.s.df["guid"] == guid] if guid and box is not None and self.s.df is not None else None
        if row is None or row.empty or self.selection_guids != [guid]:          # Auswahl inzwischen geändert
            self.page.viewer.label(None)
            return
        b = row.iloc[0]
        status = b.status if b.is_printed else "nicht_gedruckt"
        self.page.viewer.label(box, b.storey, b["name"] or b.ifc_class, status.replace("_", " "),
                               STATUS_CLASS_NAME[status])

    def _selection_ui(self) -> None:
        rows = {r["guid"]: r for r in self.table.rows}
        self.table.selected = [rows[g] for g in self.selection_guids if g in rows]
        self.table.update()
        n = len(self.selection_guids)
        self.selection = rows.get(self.selection_guids[0]) if n == 1 else None
        set_class(self.no_selection, "hidden", n > 0)
        set_class(self.bulk, "hidden", n < 2)
        self.page.detail.content.refresh()
        self.page.detail.show()

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
            self.search_text, self.only_printed_filter = "", False
            self.search_input.set_value("")
            set_class(self.only_printed_box, "an", False)
            storey = self.s.df.loc[self.s.df["guid"] == guid, "storey"]
            if self.page.floor_sel and not storey.empty and storey.iloc[0] != self.page.floor_sel:
                await self.page.select_storey(None)              # Bauteil liegt in einem anderen Geschoss
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
