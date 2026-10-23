"""Blatt 02 «Einstellungen»: Massstab, Drucker, Geschosse, Qualität, Öffnungen, Ausrichtung, Steckverbinder.

Zweck:   Jede Auswahl hier ändert eine Einstellung der Sitzung (page.setting). Der Massstab steht zuerst,
         weil er Regelset und Parameter (Qualitäten, Laibung, Steckverbinder) bestimmt.
Eingabe: die Seite (page) mit Sitzung, Datenbank und Modell-Übersicht (Geschossfarben)
Ausgabe: das Blatt 02 (Element self.sheet); content.refresh() zeichnet es nach Massstab- oder Modellwechsel neu
"""

from nicegui import ui

from config import QUALITIES, SCALES
from core.analysis.ruleset import ScaleParameters
from core.openings.windows import OPENING_MODES
from ui.texts import SCALE_NOTE
from ui.widgets import button, set_class, sheet_frame, storey_label, tag


def draft_wall_mm(min_wall_mm: float) -> float:
    """Dünnste Wand im Entwurf: auf ganze 0.8-mm-Voxel aufgerundet, mindestens zwei Voxel."""
    voxel = QUALITIES["entwurf"]
    return max(2, int(-(-min_wall_mm // voxel))) * voxel


class SheetSetup:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        with sheet_frame("Einstellungen", "02 / 05") as self.sheet:
            with ui.element("div").classes("sheet-body"):
                self.content()

    @ui.refreshable_method
    def content(self) -> None:
        """Massstab zuerst: er bestimmt Regeln und Parameter (Qualitäten, Laibung, Steckverbinder)."""
        p = self.s.parameter
        self._scale_fields()
        self._printer_fields()
        if self.s.df is not None:
            self._storey_chips()
        self._quality_fields(p)
        self._opening_fields(p)
        self._align_switch()
        self._connector_switch(p)

    def _scale_fields(self) -> None:
        self._segments("Massstab", "scale", list(SCALES))
        tag("p", SCALE_NOTE.get(self.s.scale, ""), "hint massstab-hinweis")
        tag("p", f"Der Massstab wählt das Regelset ({self.s.ruleset_name}); die Regeln je IFC-Klasse stehen in 03 Regeln.",
            "hint")

    def _printer_fields(self) -> None:
        for field_name, title, options in (("profile", "Druckerprofil", [p["name"] for p in self.s.db.profiles()]),
                                           ("material", "Material", [m["name"] for m in self.s.db.materials()])):
            with ui.element("label").classes("field"):
                tag("span", title)
                ui.select(options, value=getattr(self.s, field_name),
                          on_change=lambda e, f=field_name: self.page.setting(f, e.value)
                          ).props("outlined dense options-dense").classes("auswahl")

    def _quality_fields(self, p: ScaleParameters) -> None:
        self._segments("Qualität", "quality", list(QUALITIES) + ["auto"], allowed=set(p.qualities))
        tag("p", "Fein = 0.4 mm Voxel (Druckqualität), Entwurf = 0.8 mm (≈ 4× schneller; Wände dann mind. "
                 f"{draft_wall_mm(p.min_thickness_wall_mm):.1f} mm, weil nur ganze Voxel), "
                 "Auto = fein, bei zu grossen Modellen Entwurf."
            if "entwurf" in p.qualities else
            f"Bei {self.s.scale} nur «fein»: eine {p.min_thickness_wall_mm:.1f}-mm-Wand wäre in 0.8-mm-Voxeln "
            "zu grob für Laibungen.", "hint")

    def _opening_fields(self, p: ScaleParameters) -> None:
        captions = {"geschlossen": "voll", "ausgeschnitten": "offen", "vertieft": "vertieft"}
        self._segments("Fenster", "windows", list(OPENING_MODES), captions)
        self._segments("Türen", "doors", list(OPENING_MODES), captions)
        tag("p", "Voll = Öffnung über die ganze Wanddicke geschlossen (kein Sturz-Überhang). "
                 f"Vertieft = voll, innen und aussen {p.reveal_depth_mm:.1f} mm Laibung (in dünnen Wänden nur aussen). "
                 "Offen = ganz ausgeschnitten.", "hint")

    def _align_switch(self) -> None:
        with ui.element("div").classes("switch" + (" an" if self.s.align else "")).on(
                "click", self._toggle_align) as self.align_switch:
            self.align_text = tag("span")
            tag("i")
        self.show_alignment()

    def _connector_switch(self, p: ScaleParameters) -> None:
        with ui.element("div").classes("switch" + (" an" if self.s.connectors else "")
                                       + ("" if p.connectors_allowed else " gesperrt")).on(
                "click", self._toggle_connector) as self.connector_switch:
            tag("span", "Steckverbinder")
            tag("i")
        tag("p", "Zapfen und Löcher zwischen den Geschossteilen; wirkt auf «Pro Geschoss» und «Platte»."
            if p.connectors_allowed else
            f"Bei {self.s.scale} nicht möglich: Die Zapfen (min. 1.2 mm) passen nicht in "
            f"{p.min_thickness_wall_mm:.1f}-mm-Wände.", "hint")

    def _storey_chips(self) -> None:
        """Geschosse drucken: ein Chip je Geschoss (oberstes zuerst), gefüllt = wird gedruckt."""
        everything = self.s.storeys()
        chosen = set(everything if self.s.selected_storeys is None else self.s.selected_storeys)
        colors = {g["name"]: g["color"] for g in (self.page.overview or {}).get("storeys", [])}
        with ui.element("div").classes("field"):
            with ui.element("div").classes("field-kopf"):
                tag("span", "Geschosse drucken")
                tag("small", f"{len(chosen & set(everything))} von {len(everything)}", "hint")
                with ui.element("span").classes("chip-alle"):
                    button("", lambda: self._set_storeys(set(everything), everything), text="alle")
                    tag("span", "·")
                    button("", lambda: self._set_storeys(set(), everything), text="keine")
            with ui.element("div").classes("geschoss-chips"):
                for g in reversed(everything):
                    enabled = g in chosen
                    with ui.element("button").classes("geschoss-chip" + (" an" if enabled else "")).on(
                            "click", lambda g=g: self._set_storeys(chosen ^ {g}, everything)).props(
                            f'title="{g} {"nicht drucken" if enabled else "drucken"}"'):
                        tag("i").style(f"background: {colors.get(g, 'var(--muted)')}")
                        tag("span", storey_label(g))

    async def _set_storeys(self, chosen: set[str], everything: list[str]) -> None:
        await self.page.setting("selected_storeys",
                                None if chosen >= set(everything) else [g for g in everything if g in chosen])
        if self.page.is_alive():
            self.content.refresh()

    async def _toggle_connector(self) -> None:
        if not self.s.parameter.connectors_allowed:
            return
        await self.page.setting("connectors", not self.s.connectors)
        set_class(self.connector_switch, "an", self.s.connectors)

    async def _toggle_align(self) -> None:
        await self.page.setting("align", not self.s.align)

    def show_alignment(self) -> None:
        """Schalter «Automatisch ausrichten» mit erkanntem Winkel beschriften."""
        angle = f" ({self.s.angle:+.1f}°)" if self.s.align and self.s.ifc is not None else ""
        self.align_text.set_text("Automatisch ausrichten" + angle)
        set_class(self.align_switch, "an", self.s.align)

    def _segments(self, title: str, field_name: str, values: list[str], captions: dict | None = None,
                  allowed: set[str] | None = None) -> None:
        """Segment-Auswahl; Werte ausserhalb von ``allowed`` sind sichtbar, aber gesperrt."""
        with ui.element("div").classes("field"):
            tag("span", title)
            with ui.element("div").classes("segmented"):
                buttons = {}

                async def pick_value(w):
                    for k, b in buttons.items():
                        set_class(b, "active", k == w)
                    await self.page.setting(field_name, w)
                for w in values:
                    buttons[w] = button("active" if w == getattr(self.s, field_name) else "", lambda w=w: pick_value(w),
                                        text=(captions or {}).get(w, w))
                    if allowed is not None and w not in allowed:
                        buttons[w].props("disabled").classes("gesperrt")
