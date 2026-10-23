"""Detailfeld eines gewählten Bauteils (Blatt 03, Tab «Bauteile»).

Zweck:   Zeigt Dicke real und im Modell, womit das Bauteil gedruckt wird, die wirksame Regel und die
         Ausnahme nur für dieses Bauteil. Die Knöpfe ändern Regel oder Ausnahme; die Kopfzeile klappt das Feld ein.
Eingabe: die Seite (page) mit Sitzung und das Blatt «Bauteile» (elements) mit der Auswahl
Ausgabe: das Detailfeld (<aside class="detail">); leer, solange kein einzelnes Bauteil gewählt ist
"""

import math

import pandas as pd
from nicegui import ui

from ui.texts import EXCEPTION_BUTTONS, STATUS_CLASS_NAME
from ui.widgets import action_buttons, button, remember, saved, set_class, tag


class Detail:
    def __init__(self, page, elements):
        self.page = page
        self.s = page.s
        self.elements = elements
        self.is_open = bool(saved("detail_offen", True))
        set_class(elements.tab, "detail-zu", not self.is_open)
        with ui.element("aside").classes("detail"):
            self.content()

    @ui.refreshable_method
    def content(self) -> None:
        if not self.elements.selection or self.s.df is None:
            return
        row = self.s.df[self.s.df["guid"] == self.elements.selection["guid"]]
        if row.empty:
            return
        b = row.iloc[0]
        status = STATUS_CLASS_NAME[b.status] if b.is_printed else "skip"
        with ui.element("div").classes("detail-inner" + ("" if self.is_open else " zu")):
            self._header(b, status)
            self._thickness_box(b, status)
            self._rule_buttons(b)
            self._exception_buttons(b)

    def _toggle(self) -> None:
        self.is_open = not self.is_open
        remember("detail_offen", self.is_open)
        set_class(self.elements.tab, "detail-zu", not self.is_open)
        self.content.refresh()

    def _header(self, b: pd.Series, status: str) -> None:
        """Kopfzeile: Status, Aktion, Name, Klasse; ein Klick klappt das Feld ein, × hebt die Auswahl auf."""
        with ui.element("div").classes("detail-kopf").on("click", self._toggle).props(
                f'title="{"Detail einklappen" if self.is_open else "Detail aufklappen"}"'):
            tag("span", "▾" if self.is_open else "▸", "detail-pfeil")
            with ui.element("div").classes("detail-titel"):
                status_text = (b.status if b.is_printed else "nicht_gedruckt").replace("_", " ").upper()
                tag("small", f"{status_text} · {b.action.upper()}", f"kicker {status}")
                tag("h3", b["name"] or b.ifc_class)
                tag("p", f"{b.ifc_class} · {b.storey} · {b.category}")
            with ui.element("button").classes("detail-close").on(        # .stop: Kopfzeile nicht umschalten
                    "click.stop", lambda: self.elements.set_selection([])).props('title="Auswahl aufheben"'):
                tag("span", "×")

    def _thickness_box(self, b: pd.Series, status: str) -> None:
        """Dicke real und im Modell, Balken zur Mindestwand und womit das Bauteil gedruckt wird."""
        min_wall = self.s.profile_data["min_wall_mm"]
        d = 0.0 if math.isnan(b.thickness_model_mm) else b.thickness_model_mm
        with ui.element("div").classes("detail-box"):
            for left, right in (("Dicke real", f"{d * self.s.scale_denominator:.0f} mm"),
                                (f"im Modell {self.s.scale}", f"{d:.2f} mm")):
                with ui.element("div"):
                    tag("span", left)
                    tag("span", right, status)
            with ui.element("span").classes(f"dicke-balken {status}"):
                tag("i").style(f"width: {min(100, d / (2 * min_wall) * 100):.0f}%")
            with ui.element("div"):
                tag("span", "Mindestwand (Profil)")
                tag("span", f"{min_wall:.2f} mm")
            with ui.element("div").classes("summe"):
                tag("span", "wird gedruckt mit")
                tag("span", self._printed_with(b, d, min_wall))

    def _printed_with(self, b: pd.Series, d: float, min_wall: float) -> str:
        """Dicke bzw. Art, mit der das Bauteil gedruckt wird (je nach Aktion der Regel)."""
        railing_band_mm = self.s.parameter.min_thickness_railing_mm
        if b.package >= 0 and b.is_printed:   # Wände/Decken: Paket auf ganze Voxel, mind. Mindestdicke
            return f"≈ {max(d, self.s.package_min_thickness(b.guid)):.2f} mm (Paket)"
        return {"entfernen": "–", "fuellen": f"Füllquader {min_wall:.2f} mm",
                "band": f"Band {railing_band_mm:.1f} mm" if railing_band_mm else "– (keine Bänder)",
                "verdicken": f"{max(d, min_wall):.2f} mm", "behalten": f"{d:.2f} mm"}[b.action]

    def _rule_buttons(self, b: pd.Series) -> None:
        """Aktionsknöpfe der wirksamen Regel (gilt für alle Bauteile dieser Klasse)."""
        with ui.element("div"):
            rule = b.rule or b.ifc_class                  # wirksame Regel: eigene, geerbte oder die des Ganzen
            tag("div", f"Regel für {rule}" + ("" if rule == b.ifc_class else f" (gilt für {b.ifc_class})"),
                "detail-label")
            action_buttons(rule, b.action, self.page.sheet_rules.set_rule, b.category)

    def _exception_buttons(self, b: pd.Series) -> None:
        """Ausnahme nur für dieses Bauteil: drucken, nicht drucken oder wie Regel."""
        with ui.element("div"):
            own = self.s.exceptions.get(b.guid)
            tag("div", "Nur dieses Bauteil" + (" (übersteuert)" if own else ""), "detail-label")
            with ui.element("div").classes("regel-aktionen"):
                for action, text in EXCEPTION_BUTTONS:
                    button("active" if own == action else "", lambda a=action: self.elements.set_exception(b.guid, a),
                           text=text)
