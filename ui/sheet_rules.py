"""Blatt 03 «Regeln», Tab «IFC-Klassen»: die Regel je IFC-Klasse wählen.

Zweck:   Listet die Regeln des Regelsets (= Massstab, gewählt in der Kopfzeile) nach Gruppen (Tragwerk, Erschliessung,
         Ausbau · Öffnungen, Sonstiges) mit einem Radio-Punkt je Aktion, dazu die Klassen des Modells ohne eigene Regel
         und eine Suche im ganzen IFC-Schema. «+» an einer Regel legt eine Regel mit Bedingung an (aussen, innen,
         tragend, dünner als … mm; core/analysis/ruleset.py), «×» löscht sie wieder. Ist in der Matrix ein Geschoss gewählt, zeigen beide Tabs nur dessen
         Bauteile (oranger Filterhinweis). Im selben Blatt sitzt der Tab «Bauteile» (sheet_elements.py); ein Griff
         rechts ausserhalb des Blattes verstellt die Breite des aktiven Tabs.
Eingabe: die Seite (page) mit Sitzung, Datenbank und Geschoss-Auswahl (page.floor_sel)
Ausgabe: das Blatt 03 (Element self.sheet); jede Regel wird gespeichert und das Modell neu analysiert
"""

import pandas as pd
from nicegui import events, run, ui

from core.analysis.ruleset import check_key, condition_label, rule_class, rule_reason, split_key
from core.ifc.schema import all_classes
from ui.sheet_elements import SheetElements
from ui.texts import GROUP_OF, GROUP_ORDER, GROUP_WITHOUT_RULE, HANDLE_JS
from ui.widgets import button, popup, radio_buttons, remember, saved, set_class, sheet_frame, storey_label, tag

MAX_SCHEMA_ROWS = 40     # Treffer der Schema-Suche, die höchstens als Zeilen erscheinen
SIMPLE_CONDITIONS = ("aussen", "innen", "tragend")       # ohne Wert; dazu «duenner_als:<mm>» mit Zahlenfeld
THIN_DEFAULT_MM = 0.8                                     # Vorschlag im Zahlenfeld «dünner als … mm»
TABS = (("klassen", "IFC-Klassen"), ("bauteile", "Bauteile"))


def class_name_label(name: str, note: str, in_model: bool = True, italic: bool = False) -> None:
    """Klassenname, gekürzt mit «…»; Name und Hinweis erscheinen beim Darüberfahren."""
    css = "klasse-name" + (" im-modell" if in_model else "") + (" kursiv" if italic else "")
    with tag("span", name, css):
        popup(f"{name}\n{note}" if note else name)


def own_rule_counts(df: pd.DataFrame | None) -> dict[str, int]:
    """Anzahl Bauteile je eigener Regel: Regel «IfcSlab» zählt IfcSlab-Bauteile, geerbte Klassen zählen nicht mit."""
    if df is None or df.empty:
        return {}
    own = df[df["rule"].map(rule_class) == df["ifc_class"]]
    return own["rule"].value_counts().to_dict()


class SheetRules:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.search_text = ""                    # Suchtext im Regelblatt
        self.footer_text = None                  # Fusszeile entsteht erst nach der ersten Liste
        self.condition_open: str | None = None   # Regel, unter der die Bedingungs-Auswahl offen ist
        self.elements: SheetElements | None = None
        self.tab = saved("tab_03", "klassen") if saved("tab_03", "klassen") in dict(TABS) else "klassen"
        with sheet_frame("Regeln", "sheet-regeln") as self.sheet:
            with ui.element("div").classes("blatt-tabs"):
                with ui.element("div"):
                    self.tab_buttons = {name: button("", lambda n=name: self.select_tab(n), text=text)
                                        for name, text in TABS}
            self.filter_hint()
            with ui.element("div").classes("tab-inhalt") as classes_tab:
                self._classes_tab()
            self.elements = SheetElements(page)
            self.tabs = {"klassen": classes_tab, "bauteile": self.elements.tab}
            with ui.element("div").classes("griff").on("mousedown", js_handler=HANDLE_JS):
                for _ in range(3):
                    tag("i")
                popup("Breite ziehen")
        self._show_tab(self.tab)

    def _classes_tab(self) -> None:
        """Tab «IFC-Klassen»: Suchfeld, Kopfzeile, Regelliste und Fusszeile."""
        with ui.element("div").classes("regel-suche"):
            ui.input(placeholder="IFC-Klasse suchen, z.B. «column» oder «IfcRamp»",
                     on_change=self._search_rules).props("dense outlined clearable debounce=150").classes("suchfeld")
        with ui.element("div").classes("regel-kopf"):
            for t in ("IFC-KLASSE", "BEH.", "VERD.", "FÜLL.", "BAND", "ENTF."):
                tag("span", t)
        self.rule_list()
        with ui.element("div").classes("sheet-foot"):
            self.footer_text = tag("p", f"Regeln für {self.s.scale} – ein Klick ändert sie sofort.", "hint")
            button("pill-knopf", self._reset_rules, text="Auf Standard zurücksetzen").mark("regeln-zuruecksetzen")

    # --- Tabs und Filterhinweis --------------------------------------------------------------

    def select_tab(self, name: str) -> None:
        """Tab «klassen» oder «bauteile» anzeigen (und für den nächsten Besuch merken)."""
        self._show_tab(name)
        self.page.detail.show()
        self.page.panel.show_legend()

    def _show_tab(self, name: str) -> None:
        self.tab = name if name in self.tabs else "klassen"
        remember("tab_03", self.tab)
        for n, content in self.tabs.items():
            set_class(content, "active", n == self.tab)
            set_class(self.tab_buttons[n], "active", n == self.tab)
        set_class(self.sheet, "tab-bauteile", self.tab == "bauteile")    # Breite des Tabs
        self.show_filter()

    def show_filter(self) -> None:
        self.filter_hint.refresh()

    @ui.refreshable_method
    def filter_hint(self) -> None:
        """Oranger Hinweis über beiden Tabs, solange in der Matrix ein Geschoss gewählt ist."""
        floor = self.page.floor_sel
        if not floor or self.elements is None or self.s.df is None:
            return
        color = next((g["color"] for g in (self.page.overview or {}).get("storeys", []) if g["name"] == floor),
                     "var(--muted)")
        if self.tab == "klassen":
            groups, without = self._class_rows("")
            note = f"{sum(map(len, groups.values())) + len(without)} Klassen mit Bauteilen"
        else:
            note = f"{len(self.elements.table.rows)} Bauteile"
        with ui.element("div").classes("filterhinweis"):
            tag("i").style(f"background: {color}")
            tag("span", f"Gefiltert auf {storey_label(floor)} · {note}")
            button("", lambda: self.page.select_storey(None), text="Filter aufheben ×").mark("filter-aufheben")

    # --- Regelliste --------------------------------------------------------------------------

    async def _reset_rules(self) -> None:
        self.s.db.reset_rules(self.s.ruleset_name)
        self.page.show_message(f"Regeln {self.s.ruleset_name} auf Standard zurückgesetzt.", "ok")
        await self.set_rule(None, None)

    def _search_rules(self, e: events.ValueChangeEventArguments) -> None:
        self.search_text = (e.value or "").strip()
        self.rule_list.refresh()

    def _class_rows(self, query: str) -> tuple[dict[str, list], list[dict]]:
        """Eigene Regeln je Gruppe [(Regel, Anzahl)] und Klassen ohne eigene Regel – bei gewähltem Geschoss nur die
        Klassen mit Bauteilen darin, Anzahlen für dieses Geschoss."""
        floor = self.page.floor_sel
        df = self.s.df
        if df is not None and floor:
            df = df[df["storey"] == floor]
        counts = own_rule_counts(df)
        groups: dict[str, list] = {g: [] for g in GROUP_ORDER}
        for rule in sorted(self.s.rules, key=lambda r: split_key(r["ifc_class_name"])):   # Bedingungen unter ihrer Regel
            name = rule["ifc_class_name"]
            n = counts.get(name, 0)
            if query in name.lower() and (n or not floor):
                groups[GROUP_OF.get(rule["category"], "SONSTIGES")].append((rule, n))
        without = [k for k in self.s.classes_without_rule(floor) if query in k["ifc_class_name"].lower()]
        return groups, without

    @ui.refreshable_method
    def rule_list(self) -> None:
        """Eigene Regeln nach Gruppen, Klassen ohne Regel und – bei einer Suche – passende Klassen des IFC-Schemas."""
        query = self.search_text.lower()
        if self.footer_text is not None:
            self.footer_text.set_text(f"Regeln für {self.s.scale} – ein Klick ändert sie sofort.")
        groups, without = self._class_rows(query)
        with ui.element("div").classes("regel-liste duenn"):
            for group in GROUP_ORDER:
                if groups[group]:
                    tag("div", group, "regel-gruppe")
                for rule, n in groups[group]:
                    self._rule_row(rule, n)
            if without:
                tag("div", GROUP_WITHOUT_RULE, "regel-gruppe")
                actions = {r["ifc_class_name"]: r["action"] for r in self.s.rules}
            for k in without:
                self._row_without_rule(k, actions.get(k["rule"], ""))
            more = self._schema_rows(query, without) if query else []
            if query and not (any(groups.values()) or without or more):
                tag("p", f"Keine IFC-Klasse enthält «{self.search_text}».", "hint")
        self.show_filter()

    def _rule_row(self, rule: dict, n: int) -> None:
        name = rule["ifc_class_name"]
        base, condition = split_key(name)
        with ui.element("div").classes("regel-zeile" + (" bedingt" if condition else "")):
            with ui.element("span").classes("regel-name"):
                reason = rule_reason(self.s.ruleset_name, name, rule["action"])
                label = f"{base} · {condition_label(condition)}" if condition else name
                class_name_label(label, f"{rule['category']} · {reason}" if reason else rule["category"], in_model=n > 0)
                if n:
                    tag("small", f"{n}×")
                if condition:
                    button("regel-extra", lambda: self._delete_rule(name), text="×").props(
                        'title="Regel mit Bedingung löschen"').mark(f"regel-loeschen-{name}")
                else:
                    button("regel-extra", lambda: self._toggle_conditions(name), text="+").props(
                        'title="Regel mit Bedingung anlegen"').mark(f"bedingung-{name}")
            radio_buttons(name, rule["action"], self.set_rule, rule["category"])
        if not condition and self.condition_open == name:
            self._condition_panel(rule)

    def _condition_panel(self, rule: dict) -> None:
        """Auswahl unter einer Regel: legt «Schlüssel[Bedingung]» mit der Aktion und Kategorie der Regel an."""
        with ui.element("div").classes("regel-bedingungen"):
            tag("span", "Nur für Bauteile, die", "hint")
            for condition in SIMPLE_CONDITIONS:
                button("pill-knopf klein", lambda c=condition: self._add_condition(rule, c),
                       text=condition_label(condition)).mark(f"bedingung-{condition}")
            with ui.element("span").classes("bedingung-duenn"):
                thin = button("pill-knopf klein", lambda: self._add_condition(rule, f"duenner_als:{limit.value or 0:g}"),
                              text="dünner als").mark("bedingung-duenner_als")
                limit = ui.number(value=THIN_DEFAULT_MM, min=0.1, step=0.1, format="%.1f").props(
                    "dense outlined borderless hide-bottom-space").classes("bedingung-zahl")
                thin.props('title="Grenzwert am Modell in mm"')
                tag("span", "mm", "hint")

    def _toggle_conditions(self, name: str) -> None:
        self.condition_open = None if self.condition_open == name else name
        self.rule_list.refresh()

    async def _add_condition(self, rule: dict, condition: str) -> None:
        key = f"{rule['ifc_class_name']}[{condition}]"
        try:
            check_key(key)
        except ValueError as error:
            self.page.show_message(str(error), "warn")
            return
        self.condition_open = None
        self.page.show_message(f"Regel {key} angelegt – jetzt ihre Aktion wählen.", "ok")
        await self.set_rule(key, rule["action"], rule["category"])

    async def _delete_rule(self, name: str) -> None:
        self.s.db.delete_rule(self.s.ruleset_name, name)
        await self.set_rule(None, None)

    def _row_without_rule(self, k: dict, rule_action: str) -> None:
        """Klasse des Modells ohne eigene Regel, mit der Regel, die stattdessen gilt (gestrichelter Punkt).

        ``rule_action``: Aktion dieser Regel – die Begründung gilt der Regel, nicht dem Bauteil (Umgebung, Ausnahmen).
        """
        with ui.element("div").classes("regel-zeile"):
            with ui.element("span").classes("regel-name"):
                note = "Im Modell ohne eigene Regel – ein Klick legt sie an"
                if reason := rule_reason(self.s.ruleset_name, k["rule"], rule_action):
                    note += f"\nWie {k['rule']}: {reason}"
                class_name_label(k["ifc_class_name"], note, italic=True)
                tag("small", f"{k['count']}× · " + (f"wie {k['rule']}" if k["rule"] else "keine Regel"))
            radio_buttons(k["ifc_class_name"], k["action"], self.set_rule, k["category"], inherited=True)

    def _schema_rows(self, query: str, without_rule: list[dict]) -> list[str]:
        """Suche im ganzen IFC-Schema: Klassen, die (noch) nicht in der Liste stehen. Rückgabe: alle Treffer."""
        shown = {r["ifc_class_name"] for r in self.s.rules} | {k["ifc_class_name"] for k in without_rule}
        schema = self.s.ifc.schema_id if self.s.ifc is not None else "IFC4"
        more = [k for k in all_classes(schema) if query in k.lower() and k not in shown]
        if more:
            tag("p", f"Weitere IFC-Klassen im Schema {schema} – Regel wählen, um sie hinzuzufügen:", "hint")
        for name in more[:MAX_SCHEMA_ROWS]:
            with ui.element("div").classes("regel-zeile"):
                with ui.element("span").classes("regel-name"):
                    class_name_label(name, "noch keine Regel", in_model=False)
                    tag("small", "noch keine Regel")
                radio_buttons(name, "", self.set_rule)
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
                self.page.detail.content.refresh()
