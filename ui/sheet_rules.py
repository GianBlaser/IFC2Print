"""Blatt 03 «Regeln», Tab «IFC-Klassen»: die Regel je IFC-Klasse wählen.

Zweck:   Listet die Regeln des Regelsets (= Massstab) mit fünf Aktionsknöpfen je Klasse, dazu die Klassen des
         Modells ohne eigene Regel und eine Suche im ganzen IFC-Schema. Im selben Blatt sitzt der Tab «Bauteile»
         (sheet_elements.py); ein Griff am rechten Rand verstellt die Breite des Blattes.
Eingabe: die Seite (page) mit Sitzung und Datenbank
Ausgabe: das Blatt 03 (Element self.sheet); jede Regel wird gespeichert und das Modell neu analysiert
"""

from nicegui import events, run, ui

from config import SCALES
from core.ifc.schema import all_classes
from ui.sheet_elements import SheetElements
from ui.texts import HANDLE_JS, WIDTH_03
from ui.widgets import action_buttons, button, remember, saved, set_class, sheet_frame, tag

MAX_SCHEMA_ROWS = 40     # Treffer der Schema-Suche, die höchstens als Zeilen erscheinen


def class_name_label(name: str) -> None:
    """Klassenname, gekürzt mit «…»; der ganze Name erscheint beim Darüberfahren."""
    with tag("span", name, "klasse-name"):
        ui.tooltip(name).classes("tip")


class SheetRules:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.search_text = ""                    # Suchtext im Regelblatt
        self.footer_text = None                  # Fusszeile entsteht erst nach der ersten Liste
        with sheet_frame("Regeln", "03 / 05", "sheet-regeln") as self.sheet:
            self._header()
            with ui.element("div").classes("tab-inhalt") as classes_tab:
                self._classes_tab()
            self.elements = SheetElements(page)
            self.tabs = {"klassen": classes_tab, "bauteile": self.elements.tab}
            ui.element("div").classes("blatt-griff").on("mousedown", js_handler=HANDLE_JS)
        self.sheet.style(f"--breite-03: {saved('breite_03', WIDTH_03[0])}px")
        ui.on("breite_03", lambda e: remember("breite_03", int(e.args)))
        self.select_tab(saved("tab_03", "klassen"))

    def _header(self) -> None:
        """Regelset (= Massstab) und die beiden Tabs."""
        with ui.element("div").classes("regelset-kopf"):
            self.rule_set_selection = ui.select(list(SCALES), value=self.s.scale, on_change=self._rule_set_selected
                                                ).props('outlined dense options-dense title="Regelset = Massstab"'
                                                        ).classes("auswahl regelset")
            with ui.element("div").classes("blatt-tabs"):
                self.tab_buttons = {name: button("", lambda n=name: self.select_tab(n), text=text)
                                    for name, text in (("klassen", "IFC-Klassen"), ("bauteile", "Bauteile"))}

    def _classes_tab(self) -> None:
        """Tab «IFC-Klassen»: Suchfeld, Kopfzeile, Regelliste und Fusszeile."""
        with ui.element("div").classes("regel-suche"):
            ui.input(placeholder="IFC-Klasse suchen, z.B. «column» oder «IfcRamp»",
                     on_change=self._search_rules).props("dense outlined clearable debounce=150").classes("suchfeld")
        with ui.element("div").classes("regel-kopf"):
            for t in ("IFC-KLASSE", "BEHALTEN", "VERDICKEN", "FÜLLEN", "BAND", "ENTFERNEN"):
                tag("span", t)
        self.rule_list()
        with ui.element("div").classes("sheet-foot"):
            self.footer_text = tag("p", f"Regeln für {self.s.scale} – ein Klick ändert sie sofort.", "hint")
            button("btn btn-ghost btn-pill", self._reset_rules, text="Auf Standard zurücksetzen")

    def select_tab(self, name: str) -> None:
        """Tab «klassen» oder «bauteile» anzeigen (und für den nächsten Besuch merken)."""
        name = name if name in self.tabs else "klassen"
        remember("tab_03", name)
        for n, content in self.tabs.items():
            set_class(content, "active", n == name)
            set_class(self.tab_buttons[n], "active", n == name)

    def show_scale(self) -> None:
        """Regelset-Auswahl auf den Massstab der Sitzung setzen (02 und 03 bleiben synchron)."""
        self.rule_set_selection.set_value(self.s.scale)

    async def _rule_set_selected(self, e: events.ValueChangeEventArguments) -> None:
        if e.value and e.value != self.s.scale:      # programmatisch gesetzt (aus 02) → nichts tun
            await self.page.setting("scale", e.value)

    async def _reset_rules(self) -> None:
        self.s.db.reset_rules(self.s.ruleset_name)
        self.page.show_message(f"Regeln {self.s.ruleset_name} auf Standard zurückgesetzt.", "ok")
        await self.set_rule(None, None)

    def _search_rules(self, e: events.ValueChangeEventArguments) -> None:
        self.search_text = (e.value or "").strip()
        self.rule_list.refresh()

    @ui.refreshable_method
    def rule_list(self) -> None:
        """Eigene Regeln, Klassen ohne Regel und – bei einer Suche – passende Klassen des IFC-Schemas."""
        query = self.search_text.lower()
        if self.footer_text is not None:
            self.footer_text.set_text(f"Regeln für {self.s.scale} – ein Klick ändert sie sofort.")
        with ui.element("div").classes("regel-liste"):
            rules = [r for r in self.s.rules if query in r["ifc_class_name"].lower()]
            for rule in rules:
                self._rule_row(rule["ifc_class_name"], rule["action"])
            without_rule = [k for k in self.s.classes_without_rule() if query in k["ifc_class_name"].lower()]
            self._rows_without_rule(without_rule)
            if not query:
                return
            more = self._schema_rows(query, without_rule)
            if not (rules or without_rule or more):
                tag("p", f"Keine IFC-Klasse enthält «{self.search_text}».", "hint")

    def _rule_row(self, name: str, action: str) -> None:
        with ui.element("div").classes("regel-zeile"):
            with ui.element("code"):
                class_name_label(name)
            action_buttons(name, action, self.set_rule)

    def _rows_without_rule(self, entries: list[dict]) -> None:
        """Klassen des Modells ohne eigene Regel, mit der Regel, die stattdessen gilt."""
        if entries:
            tag("p", "Im Modell ohne eigene Regel – ein Klick legt sie an:", "hint")
        for k in entries:
            with ui.element("div").classes("regel-zeile"):
                with ui.element("code").classes("ohne-regel"):
                    class_name_label(k["ifc_class_name"])
                    tag("small", f"{k['count']}× · " + (f"wie {k['rule']}" if k["rule"] else "keine Regel"))
                action_buttons(k["ifc_class_name"], k["action"], self.set_rule, k["category"])

    def _schema_rows(self, query: str, without_rule: list[dict]) -> list[str]:
        """Suche im ganzen IFC-Schema: Klassen, die (noch) nicht in der Liste stehen. Rückgabe: alle Treffer."""
        shown = {r["ifc_class_name"] for r in self.s.rules} | {k["ifc_class_name"] for k in without_rule}
        schema = self.s.ifc.schema_id if self.s.ifc is not None else "IFC4"
        more = [k for k in all_classes(schema) if query in k.lower() and k not in shown]
        if more:
            tag("p", f"Weitere IFC-Klassen im Schema {schema} – Regel wählen, um sie hinzuzufügen:", "hint")
        for name in more[:MAX_SCHEMA_ROWS]:
            with ui.element("div").classes("regel-zeile neu"):
                with ui.element("code").classes("ohne-regel"):
                    class_name_label(name)
                    tag("small", "noch keine Regel")
                action_buttons(name, "", self.set_rule)
        if len(more) > MAX_SCHEMA_ROWS:
            tag("p", f"… und {len(more) - MAX_SCHEMA_ROWS} weitere – Suche genauer eingeben.", "hint")
        return more

    async def set_rule(self, ifc_class: str | None, action: str | None, category: str = "Sonstiges") -> None:
        """Regel setzen (gespeichert beim aktuellen Massstab); eine neue Regel übernimmt die Kategorie,
        die bisher (geerbt) galt. Ohne Klasse: nur neu analysieren (nach dem Zurücksetzen)."""
        if ifc_class is not None:
            self.s.db.set_action(self.s.ruleset_name, ifc_class, action, category)
        self.rule_list.refresh()                     # sofortige Rückmeldung; nach der Analyse nochmals
        if self.s.ifc is not None:
            await run.io_bound(self.s.analyse)
            if not self.page.is_alive():
                return
            await self.page.show_analysis()
            if self.elements.selection:
                self.elements.detail.content.refresh()
