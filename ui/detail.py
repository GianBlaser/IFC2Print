"""Detail-Karte eines gewählten Bauteils, rechts neben Blatt 03.

Zweck:   Zeigt Status und Aktion, Name, Klasse, Geschoss und Kategorie, die Dicke real und im Modell, die Mindestwand
         und womit das Bauteil gedruckt wird, dazu die Ausnahme nur für dieses Bauteil (drucken, nicht drucken, wie
         Regel). Die Regel selbst stellt man im Tab «IFC-Klassen».
Eingabe: die Seite (page) mit Sitzung, offenem Blatt und dem Tab «Bauteile» (page.sheet_elements) mit der Auswahl
Ausgabe: <aside class="detail-karte"> ausserhalb der Blätter; sichtbar, solange 03 offen und genau ein Bauteil gewählt ist
"""

import math

import pandas as pd
from nicegui import ui

from ui.texts import EXCEPTION_BUTTONS, STATUS_CLASS_NAME
from ui.widgets import button, set_class, tag


class Detail:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        with ui.element("aside").classes("detail-karte hidden") as self.card:
            self.content()

    @property
    def elements(self):
        return self.page.sheet_elements

    def show(self) -> None:
        """Ein- oder ausblenden; die Karte steht 44 px rechts neben dem aktiven Tab (Platz für den Breitengriff)."""
        visible = self.page.open_sheet == "regeln" and self.elements.selection is not None
        set_class(self.card, "hidden", not visible)
        set_class(self.card, "bauteile-tab", self.page.sheet_rules.tab == "bauteile")

    @ui.refreshable_method
    def content(self) -> None:
        if not self.elements.selection or self.s.df is None:
            return
        row = self.s.df[self.s.df["guid"] == self.elements.selection["guid"]]
        if row.empty:
            return
        b = row.iloc[0]
        status = b.status if b.is_printed else "nicht_gedruckt"
        css_class = STATUS_CLASS_NAME[status]
        self._header(b, status, css_class)
        self._facts(b, css_class)
        self._exception_buttons(b)

    def _header(self, b: pd.Series, status: str, css_class: str) -> None:
        """Kicker «STATUS · AKTION», Name, Klasse · Geschoss · Kategorie und × (hebt die Auswahl auf)."""
        predefined = b.get("predefined_type", "") or ""
        ifc_class = b.ifc_class + (f".{predefined}" if predefined and predefined != "NOTDEFINED" else "")
        with ui.element("div").classes("detail-kopf"):
            with ui.element("div").classes("detail-titel"):
                tag("small", f"{status.replace('_', ' ')} · {b.action}", f"text-{css_class}")
                tag("h3", b["name"] or b.ifc_class)
                tag("p", f"{ifc_class} · {b.storey} · {b.category}")
            button("detail-close", lambda: self.elements.set_selection([]), text="×").props(
                'aria-label="Auswahl aufheben"')

    def _facts(self, b: pd.Series, css_class: str) -> None:
        """Dicke real und im Modell, Mindestwand des Profils und womit das Bauteil gedruckt wird."""
        min_wall = self.s.profile_data["min_wall_mm"]
        d = 0.0 if math.isnan(b.thickness_model_mm) else b.thickness_model_mm
        with ui.element("div").classes("fakten"):
            for word, value, color in (("Dicke real", f"{d * self.s.scale_denominator:.0f} mm", ""),
                                       (f"im Modell {self.s.scale}", f"{d:.2f} mm", f"text-{css_class}"),
                                       ("Mindestwand", f"{min_wall:.2f} mm", ""),
                                       ("Gedruckt mit", self._printed_with(b, d, min_wall), "")):
                with ui.element("div"):
                    tag("small", word)
                    tag("b", value, color)

    def _printed_with(self, b: pd.Series, d: float, min_wall: float) -> str:
        """Dicke bzw. Art, mit der das Bauteil gedruckt wird (je nach Aktion der Regel)."""
        railing_band_mm = self.s.parameter.min_thickness_railing_mm
        if b.package >= 0 and b.is_printed:   # Wände/Decken: Paket auf ganze Voxel, mind. Mindestdicke
            return f"≈ {max(d, self.s.package_min_thickness(b.guid)):.2f} mm (Paket)"
        return {"entfernen": "–", "fuellen": f"Füllquader {min_wall:.2f} mm",
                "band": f"Band {railing_band_mm:.1f} mm" if railing_band_mm else "– (keine Bänder)",
                "verdicken": f"{max(d, min_wall):.2f} mm", "behalten": f"{d:.2f} mm"}[b.action]

    def _exception_buttons(self, b: pd.Series) -> None:
        """Ausnahme nur für dieses Bauteil: drucken, nicht drucken oder wie Regel."""
        own = self.s.exceptions.get(b.guid)
        with ui.element("div").classes("ausnahme"):
            tag("span", "Nur dieses Bauteil" + (" (übersteuert)" if own else ""))
            with ui.element("div").classes("ausnahme-seg"):
                for action, text in EXCEPTION_BUTTONS:
                    button("active" if own == action else "", lambda a=action: self.elements.set_exception(b.guid, a),
                           text=text)
