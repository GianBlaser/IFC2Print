"""Matrix im Panel: Geschoss × Status.

Zweck:   Zählt je Geschoss (oberstes oben), wie viele Bauteile druckbar, kritisch, nicht druckbar oder nicht gedruckt
         sind. Ein Klick auf Zelle, Zeile oder Spalte öffnet 03 › Bauteile mit diesem Filter und zeigt im Viewer nur
         diese Bauteile («alle Bauteile zeigen» hebt das auf), ein Klick auf das Farbquadrat blendet das Geschoss aus,
         die Maus über einer Zeile hebt das Geschoss im Viewer hervor.
Eingabe: die Seite (page) mit Sitzung (status_matrix, metrics), Viewer und Modell-Übersicht (Geschossfarben)
Ausgabe: der Matrix-Block im Panel; content.refresh() zeichnet ihn neu
"""

from nicegui import ui

from ui.texts import MATRIX_COLUMNS, STATUS_SHORT
from ui.widgets import button, remember, storey_label, tag


class Matrix:
    def __init__(self, page):
        self.page = page
        self.s = page.s

    @ui.refreshable_method
    def content(self) -> None:
        """Zellfarbe = Anteil am Spaltenmaximum.
        Nur ui.element("div"): ui.grid/ui.row würden Spalten und Lücken mit eigenen Klassen überschreiben."""
        rows = list(reversed(self.s.status_matrix()))
        colors = {g["name"]: g["color"] for g in (self.page.overview or {}).get("storeys", [])}
        maxima = {s: max((z[s] for z in rows), default=0) or 1 for s, _, _ in MATRIX_COLUMNS}
        hidden = self.page.viewer.hidden
        with ui.element("div").classes("matrix"):
            self._header()
            with ui.element("div").classes("matrix-liste"):
                for z in rows:
                    self._row(z, colors.get(z["storey"], "var(--muted)"), maxima, hidden)
            self._total()
        if hidden:
            button("stapel-alle", lambda: self._hide(set()), text="alle Geschosse zeigen")
        if self.page.viewer.only_selection:
            button("stapel-alle", self._show_all, text="alle Bauteile zeigen").mark("matrix-alle-bauteile")

    def _header(self) -> None:
        """Kopfzeile: eine Spalte je Status; ein Klick zeigt alle Bauteile mit diesem Status."""
        with ui.element("div").classes("matrix-kopf"):
            tag("span", "Geschoss")
            for status, text, css_class in MATRIX_COLUMNS:
                button(css_class, lambda st=status: self._show(status=st), text=text).props(
                    f'title="alle «{STATUS_SHORT[status]}» zeigen"').mark(f"matrix-{status}")
            tag("span", "Σ")

    def _row(self, z: dict, color: str, maxima: dict[str, int], hidden: set[str]) -> None:
        """Eine Geschosszeile: Name mit Farbquadrat, je Status eine Zelle, Summe."""
        g = z["storey"]
        off_suffix = " aus" if g in hidden else ""
        with ui.element("div").classes("matrix-zeile" + off_suffix) as row:
            with ui.element("div").classes("matrix-name").props(f'title="{g}"').on(
                    "click", lambda: self._show(storey=g)):
                ui.element("i").classes("matrix-farbe").style(f"background: {color}").props(
                    f'title="{"einblenden" if off_suffix else "ausblenden"}"').on(
                    "click.stop", lambda: self._hide(hidden ^ {g}))
                tag("b", storey_label(g))
            for status, _, css_class in MATRIX_COLUMNS:
                n = z[status]
                button(f"matrix-zelle {css_class}" + ("" if n else " leer"),
                       lambda st=status: self._show(status=st, storey=g),
                       text=str(n) if n else "·").style(f"--anteil: {n / maxima[status]:.2f}")
            tag("span", str(sum(z[s] for s, _, _ in MATRIX_COLUMNS)), "matrix-summe")
        row.on("mouseenter", lambda: self.page.viewer.focus(g))
        row.on("mouseleave", lambda: self.page.viewer.focus(None))

    def _total(self) -> None:
        """Totalzeile: Summe je Status über alle Geschosse."""
        k = self.s.metrics()
        with ui.element("div").classes("matrix-total"):
            tag("span", "Total")
            for status, _, css_class in MATRIX_COLUMNS:
                tag("b", str(k.get(status, 0)), css_class)
            tag("span", str(k.get("total", 0) + k.get("nicht_gedruckt", 0)), "matrix-summe")

    async def _show(self, status: str | None = None, storey: str | None = None) -> None:
        """Bauteiltabelle mit diesem Filter öffnen und im Viewer nur diese Bauteile zeigen.

        In der STL-Ansicht wechselt der Viewer auf STAT: Die STL-Teile sind ganze Geschosse, einzelne Bauteile
        lassen sich dort nicht ausblenden.
        """
        if self.page.viewer.mode == "stl":
            self.page.panel.set_mode("status")
        elements = self.page.sheet_elements
        elements.show_elements(status=status, storey=storey)
        await elements.isolate(status, storey)
        if self.page.is_alive():
            self.content.refresh()                    # «alle Bauteile zeigen» erscheint

    async def _show_all(self) -> None:
        """Im Viewer wieder alle Bauteile zeigen."""
        await self.page.sheet_elements.show_all()
        if self.page.is_alive():
            self.content.refresh()

    def _hide(self, hidden: set[str]) -> None:
        """Genau diese Geschosse im Viewer ausblenden (und für den nächsten Besuch merken)."""
        self.page.viewer.hide(hidden)
        remember("versteckt", sorted(hidden))
        self.content.refresh()
