"""Kopfzeile: Titel, Umschalter Setup | Matrix, die Setup-Felder «Schritte» und die Geschoss-Karten der Matrix.

Zweck:   Im Modus Setup stehen alle Einstellungen in einer Zeile: neun nummerierte Felder in fünf Gruppen, jede Wahl
         ändert eine Einstellung der Sitzung (page.setting). Der Massstab steht zuerst, weil er Regelset und Parameter
         (Qualitäten, Laibung, Steckverbinder) bestimmt. Im Modus Matrix zeigt je Geschoss eine Karte (oberstes links),
         wie viele Bauteile druckbar, kritisch, nicht druckbar oder nicht gedruckt sind; ein Klick wählt das Geschoss
         (page.select_storey: Viewer abdunkeln, 03 filtern), die Total-Karte zählt alle bzw. das gewählte Geschoss.
Eingabe: die Seite (page) mit Sitzung, Datenbank, Viewer, Geschoss-Auswahl (page.floor_sel) und Modell-Übersicht
Ausgabe: <header class="kopf">; content.refresh() zeichnet sie neu, toggle_mode() wechselt zwischen Setup und Matrix
"""

from collections.abc import Callable

from nicegui import ui

from config import QUALITIES, SCALES
from core.analysis.ruleset import ScaleParameters, scale_reason
from ui.texts import (ALIGN_NOTE, CONNECTOR_NOTE, LEGEND, MATRIX_COLUMNS, MATRIX_SVG, OPENING_CAPTION, OPENING_PICTO,
                      QUALITY_NOTE, SETUP_SVG)
from ui.widgets import button, popup, remember, saved, set_class, storey_label, tag

MODES = ("matrix", "setup")
COMPACT_FROM = 9         # ab so vielen Geschossen: schmale Karten ohne Zahlenzeile


def scale_note(p: ScaleParameters) -> str:
    """Hinweis zum Massstab: erste Zeile die Parameter (aus der Datenbank), darunter die Begründung."""
    railing = f"Geländer als {p.min_thickness_railing_mm:g}-mm-Band" if p.min_thickness_railing_mm else "keine Bänder"
    connectors = "Steckverbinder möglich" if p.connectors_allowed else "keine Steckverbinder"
    return (f"Wände min. {p.min_thickness_wall_mm:g} mm · {railing} · Laibung {p.reveal_depth_mm:g} mm · {connectors}\n"
            f"{scale_reason(p.ruleset_name)}")


class Header:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.mode = saved("kopf", "matrix") if saved("kopf", "matrix") in MODES else "matrix"
        self.popover: str | None = None          # offenes Auswahlfeld (eines zur Zeit)
        self._pending: dict = {}                 # gewählter Wert, solange page.setting noch rechnet
        # Klick ausserhalb schliesst das Popover; liegt unter der Kopfzeile, aber über den Blättern
        self.catcher = ui.element("div").classes("klickfaenger hidden").on("click", self.close_popover)
        with ui.element("header").classes("kopf"):
            self.content()

    # --- Modus ------------------------------------------------------------------------

    def toggle_mode(self) -> None:
        self.set_mode("setup" if self.mode == "matrix" else "matrix")

    def set_mode(self, mode: str) -> None:
        self.mode, self.popover = mode, None
        remember("kopf", mode)
        self.show_mode()
        self.content.refresh()

    def show_mode(self) -> None:
        """Höhe der Kopfzeile (über die Klasse an .app), Knopf 02 in der Leiste und Legende im Viewer nachführen."""
        setup = self.mode == "setup"
        set_class(self.page.root, "kopf-setup", setup)
        set_class(self.page.root, "kopf-matrix", not setup)
        self.page.rail.show_setup(setup)
        self.page.panel.show_legend()

    def show_alignment(self) -> None:
        """Nach Analyse oder Einstellung: Werte, Sperren und Ausrichtwinkel neu zeigen."""
        self.content.refresh()

    # --- Aufbau ----------------------------------------------------------------------

    @ui.refreshable_method
    def content(self) -> None:
        set_class(self.catcher, "hidden", self.popover is None)
        with ui.element("div").classes("kopf-links"):
            with ui.element("div").classes("kopf-zeile"):
                ui.html("IFC<span>2</span>Print", sanitize=False).classes("kopf-titel").mark("titel")
                with ui.element("div").classes("umschalter"):
                    for mode, svg, text in (("setup", SETUP_SVG, "Setup"), ("matrix", MATRIX_SVG, "Matrix")):
                        with ui.element("button").classes("active" if self.mode == mode else "").on(
                                "click", lambda m=mode: self.set_mode(m)).mark(f"kopf-{mode}"):
                            ui.html(svg, sanitize=False)
                            tag("span", text)
            if self.mode == "matrix":
                self._legend()
        if self.mode == "setup":
            self._setup()
        else:
            self._matrix()

    def _legend(self) -> None:
        with ui.element("div").classes("kopf-legende"):
            for css_class, short, text in LEGEND:
                with tag("span"):
                    tag("i", "", f"fill-{css_class}")
                    tag("b", short, f"text-{css_class}")
                    tag("span", text)
        tag("span", "Karte anklicken: filtert Viewer und Regeln", "kopf-hinweis")

    # --- Modus Setup: Felder «Schritte» ------------------------------------------------------

    def _setup(self) -> None:
        p = self.s.parameter
        scale = self.value("scale")
        with ui.element("div").classes("setup"):
            with ui.element("div").classes("setup-gruppe"):
                # Hinweis zum eben gewählten Massstab, nicht zu dem, den die Sitzung noch analysiert
                with self._field(1, "Massstab", scale_note(ScaleParameters.from_row(self.s.db.scale_parameters(scale)))):
                    self._segments("scale", [(v, v) for v in SCALES])
            with ui.element("div").classes("setup-gruppe schrumpft"):
                with self._field(2, "Drucker", css_class="schrumpft"):
                    self._printers()
                with self._field(3, "Material"):
                    self._materials()
            with ui.element("div").classes("setup-gruppe"):
                with self._field(4, "Geschosse"):
                    self._storeys()
                locked = "entwurf" not in p.qualities
                with self._field(5, "Qualität", (f"Bei {scale} nur «fein»\n" if locked else "") + QUALITY_NOTE):
                    self._segments("quality", [(v, v) for v in list(QUALITIES) + ["auto"]], allowed=set(p.qualities))
            with ui.element("div").classes("setup-gruppe"):
                for step, field_name, label in ((6, "windows", "Fenster"), (7, "doors", "Türen")):
                    with self._field(step, label):
                        self._openings(field_name, p.reveal_depth_mm)
            with ui.element("div").classes("setup-gruppe"):
                angle = f" ({self.s.angle:+.1f}°)" if self.s.align and self.s.ifc is not None else ""
                with self._field(8, "Ausrichten", ALIGN_NOTE + angle):
                    self._switch(self.value("align"), self._toggle_align, "align")
                allowed = p.connectors_allowed
                note = CONNECTOR_NOTE if allowed else (f"Bei {scale} nicht möglich: Die Zapfen (min. 1.2 mm) passen "
                                                       f"nicht in {p.min_thickness_wall_mm:.1f}-mm-Wände.")
                with self._field(9, "Verbinder", note, locked=not allowed):
                    self._switch(self.value("connectors"), self._toggle_connector, "connectors")

    def value(self, field_name: str):
        """Wert eines Feldes – der eben gewählte, solange die Sitzung ihn noch übernimmt."""
        return self._pending.get(field_name, getattr(self.s, field_name))

    def _field(self, step: int, label: str, note: str = "", locked: bool = False, css_class: str = "") -> ui.element:
        """Ein Feld: Schrittnummer und Label über dem Steuerelement, Hinweis als Popup."""
        with ui.element("div").classes(f"feld {css_class}" + (" gesperrt" if locked else "")) as field:
            with tag("span", "", "feld-label"):
                tag("b", str(step))
                tag("span", label)
            if note:
                popup(note)
        return field

    def _segments(self, field_name: str, values: list[tuple[str, str]], allowed: set[str] | None = None) -> None:
        """Segment-Auswahl; Werte ausserhalb von ``allowed`` sind sichtbar, aber gesperrt."""
        with ui.element("div").classes("seg"):
            for v, caption in values:
                b = button("active" if v == self.value(field_name) else "", lambda v=v: self.pick(field_name, v),
                           text=caption).mark(f"setup-{field_name}-{v}")
                if allowed is not None and v not in allowed:
                    b.props("disabled")

    def _switch(self, enabled: bool, on_click: Callable, field_name: str) -> None:
        with ui.element("button").classes("schalter" + (" an" if enabled else "")).on("click", on_click).mark(
                f"setup-{field_name}"):
            tag("i")
            tag("span", "an" if enabled else "aus")

    def _choice(self, key: str, text: str, css_class: str = "") -> bool:
        """Auswahlknopf, der ein Popover öffnet; True, wenn dessen Popover offen ist (Inhalt folgt im Aufrufer)."""
        is_open = self.popover == key
        with ui.element("button").classes(f"auswahl-knopf {css_class}" + (" offen" if is_open else "")).on(
                "click", lambda: self.toggle_popover(key)).mark(f"setup-{key}"):
            tag("span", text)
            tag("i", "▼")
        return is_open

    def _option(self, title: str, on_click: Callable, selected: bool = False, description: str = "", meta: str = "",
                picto: list | None = None) -> ui.element:
        """Eine Zeile im Popover: optional Piktogramm, Titel mit Beschreibung, Meta rechts."""
        with ui.element("button").classes("option" + (" gewaehlt" if selected else "")).on("click", on_click) as b:
            if picto:
                with ui.element("div").classes("picto"):
                    for left, top, width, height, free in picto:
                        tag("i", "", "frei" if free else "").style(
                            f"left: {left}px; top: {top}px; width: {width}px; height: {height}px")
            with ui.element("div").classes("option-text"):
                tag("b", title)
                if description:
                    tag("small", description)
            if meta:
                tag("span", meta, "option-meta")
        return b

    def _printers(self) -> None:
        if not self._choice("profile", self.value("profile"), "drucker"):
            return
        with ui.element("div").classes("popover"):
            for p in self.s.db.profiles():
                meta = "×".join(f"{p[f'build_volume_{a}_mm']:.0f}" for a in "xyz")
                self._option(p["name"], lambda n=p["name"]: self.pick("profile", n), p["name"] == self.value("profile"),
                             meta=meta)

    def _materials(self) -> None:
        if not self._choice("material", self.value("material"), "material"):
            return
        with ui.element("div").classes("popover"):
            for m in self.s.db.materials():
                meta = f"{m['density_g_cm3']} g/cm³ · {m['price_chf_kg']:.0f} CHF/kg"
                self._option(m["name"], lambda n=m["name"]: self.pick("material", n),
                             m["name"] == self.value("material"), meta=meta)

    def _openings(self, field_name: str, reveal_depth_mm: float) -> None:
        notes = {"geschlossen": "Öffnung über die ganze Wanddicke geschlossen (kein Sturz-Überhang).",
                 "vertieft": f"Voll, innen und aussen {reveal_depth_mm:.1f} mm Laibung (in dünnen Wänden nur aussen).",
                 "ausgeschnitten": "Ganz ausgeschnitten."}
        current = self.value(field_name)
        if not self._choice(field_name, OPENING_CAPTION.get(current, current)):
            return
        with ui.element("div").classes("popover oeffnung"):
            for mode in OPENING_CAPTION:                        # voll · vertieft · offen
                self._option(OPENING_CAPTION[mode], lambda m=mode: self.pick(field_name, m), mode == current,
                             description=notes[mode], picto=OPENING_PICTO[mode])

    def _storeys(self) -> None:
        """Geschosse drucken: Wert «n von m», im Popover ein Kästchen je Geschoss (oberstes zuerst)."""
        everything = self.s.storeys() if self.s.df is not None else []
        selection = self.value("selected_storeys")
        chosen = set(everything if selection is None else selection)
        text = f"{len(chosen & set(everything))} von {len(everything)}" if everything else "–"
        if not self._choice("storeys", text) or not everything:
            return
        colors = {g["name"]: g["color"] for g in (self.page.overview or {}).get("storeys", [])}
        with ui.element("div").classes("popover geschosse"):
            with ui.element("div").classes("popover-kopf"):
                tag("span", "Geschosse drucken")
                with ui.element("span").classes("alle-keine"):
                    button("", lambda: self._set_storeys(set(everything), everything), text="alle")
                    tag("span", "·")
                    button("", lambda: self._set_storeys(set(), everything), text="keine")
            for g in reversed(everything):
                with ui.element("button").classes("option").on(
                        "click", lambda g=g: self._set_storeys(chosen ^ {g}, everything)):
                    with ui.element("span").classes("kaestchen" + (" an" if g in chosen else "")):
                        tag("i").style(f"background: {colors.get(g, 'var(--muted)')}")
                    with ui.element("div").classes("option-text"):
                        tag("b", storey_label(g))

    # --- Bedienung Setup ------------------------------------------------------------------

    def toggle_popover(self, key: str) -> None:
        self.popover = None if self.popover == key else key
        self.content.refresh()

    def close_popover(self) -> None:
        self.popover = None
        self.content.refresh()

    async def pick(self, field_name: str, value) -> None:
        """Wert setzen und Popover schliessen; die Kopfzeile zeigt die Wahl sofort, page.setting rechnet nach."""
        if value == getattr(self.s, field_name):
            self.close_popover()
            return
        self._pending[field_name] = value
        self.popover = None
        self.content.refresh()
        try:
            await self.page.setting(field_name, value)
        finally:
            self._pending.pop(field_name, None)
            if self.page.is_alive():
                self.content.refresh()

    async def _set_storeys(self, chosen: set[str], everything: list[str]) -> None:
        """Auswahl übernehmen; das Popover bleibt offen (mehrere Geschosse nacheinander an- oder abwählen)."""
        value = None if chosen >= set(everything) else [g for g in everything if g in chosen]
        self._pending["selected_storeys"] = value
        self.content.refresh()
        try:
            await self.page.setting("selected_storeys", value)
        finally:
            self._pending.pop("selected_storeys", None)
            if self.page.is_alive():
                self.content.refresh()

    async def _toggle_align(self) -> None:
        await self.pick("align", not self.s.align)

    async def _toggle_connector(self) -> None:
        if self.s.parameter.connectors_allowed:
            await self.pick("connectors", not self.s.connectors)

    # --- Modus Matrix: Geschoss-Karten und Total-Karte ------------------------------------------

    def _matrix(self) -> None:
        rows = list(reversed(self.s.status_matrix()))           # oberstes Geschoss links
        colors = {g["name"]: g["color"] for g in (self.page.overview or {}).get("storeys", [])}
        compact = len(rows) >= COMPACT_FROM
        with ui.element("div").classes("matrix"):
            with ui.element("div").classes("karten duenn"):
                for z in rows:
                    self._card(z, colors.get(z["storey"], "var(--muted)"), compact)
            self._total(rows)

    def _card(self, z: dict, color: str, compact: bool) -> None:
        """Eine Geschoss-Karte: Name und Summe, Stapelbalken und (nicht kompakt) die vier Zahlen ohne Beschriftung."""
        g = z["storey"]
        total = sum(z[s] for s, _, _ in MATRIX_COLUMNS)
        selected = g == self.page.floor_sel
        with ui.element("button").classes("karte" + (" kompakt" if compact else "") + (" gewaehlt" if selected else "")
                                          ).mark("geschoss-" + "_".join(g.split())) as card:   # ein Marker je Karte
            with ui.element("div").classes("karte-kopf"):
                tag("i").style(f"background: {color}")
                tag("b", storey_label(g))
                tag("small", str(total))
            with ui.element("div").classes("stapel"):
                for status, _, css_class in MATRIX_COLUMNS:
                    if z[status]:
                        tag("i", "", f"fill-{css_class}").style(f"width: {z[status] / total * 100:.2f}%")
            if not compact:
                with ui.element("div").classes("zahlen"):
                    for status, _, css_class in MATRIX_COLUMNS:
                        n = z[status]
                        tag("span", str(n) if n else "·", f"text-{css_class}" if n else "null")
            popup(f"{storey_label(g)}: " + " · ".join(f"{short} {z[s]}" for s, short, _ in MATRIX_COLUMNS)
                  + " – Klick wählt das Geschoss")
        card.on("click", lambda: self.page.select_storey(g))
        card.on("mouseenter", lambda: self.page.viewer.focus(g))
        card.on("mouseleave", lambda: self.page.viewer.focus(None))

    def _total(self, rows: list[dict]) -> None:
        """Total-Karte: alle Geschosse bzw. das gewählte; «× alle» hebt die Auswahl auf."""
        row = next((z for z in rows if z["storey"] == self.page.floor_sel), None)
        counts = row or {s: sum(z[s] for z in rows) for s, _, _ in MATRIX_COLUMNS}
        with ui.element("div").classes("total-karte"):
            with ui.element("div").classes("total-kopf"):
                tag("span", f"Filter {storey_label(row['storey'])}" if row else "alle Geschosse")
                if row:
                    button("", lambda: self.page.select_storey(None), text="× alle").mark("matrix-alle")
            tag("span", str(sum(counts[s] for s, _, _ in MATRIX_COLUMNS)), "total-summe")
            with ui.element("div").classes("zahlen"):
                for status, _, css_class in MATRIX_COLUMNS:
                    tag("span", str(counts[status]), f"dunkel-{css_class}")
