"""Leiste links: Kapitel 01–05, Verlauf und Theme-Schalter.

Zweck:   Die Knöpfe öffnen die Blätter; 02 schaltet die Kopfzeile zwischen Setup und Matrix um. Ein Zähler an 05 zeigt
         die Anzahl Prüfpunkte, ein Haken markiert erledigte Kapitel. Der unterste Knopf wechselt zwischen hellem und
         dunklem Theme.
Eingabe: die Seite (page) mit Sitzung; Klicks auf die Knöpfe (page.go_to, page.theme_switch)
Ausgabe: <nav class="rail">; mark() setzt Zähler und Haken, set_active() hebt den Knopf des offenen Blattes hervor,
         show_setup() den Knopf 02, solange die Kopfzeile im Modus Setup ist
"""

from nicegui import ui

from ui.texts import LOGO_SVG, STEPS
from ui.widgets import button, set_class, tag


class Rail:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.buttons = {}
        self.badges = {}
        with ui.element("nav").classes("rail"):
            ui.html(LOGO_SVG, sanitize=False).classes("rail-logo")
            for name, number, text in STEPS:
                self.buttons[name] = button("rail-btn", lambda n=name: page.go_to(n), number, text)
            tag("span", "", "trenner")
            self.buttons["pruefen"] = button("rail-btn", lambda: page.go_to("pruefen"), "05", "PRÜFEN")
            for name, k in self.buttons.items():
                with k:
                    self.badges[name] = tag("i", "", "hidden")
            tag("span", "", "rail-spacer")
            self.buttons["verlauf"] = button("rail-btn small", lambda: page.go_to("verlauf"), "↺", "VERLAUF")
            with ui.element("button").classes("rail-btn small").on("click", page.theme_switch):
                tag("i", "", "theme-dot")
                self.theme_label = tag("span", self._theme_text())

    def _theme_text(self) -> str:
        """Beschriftung des Theme-Knopfes: er zeigt, wohin er umschaltet."""
        return "HELL" if self.s.theme == "dark" else "DUNKEL"

    def show_theme(self) -> None:
        self.theme_label.set_text(self._theme_text())

    def set_active(self, name: str) -> None:
        """Den Knopf des offenen Blattes hervorheben (leerer Name: keiner); 02 folgt der Kopfzeile."""
        for n, k in self.buttons.items():
            if n != "setup":
                set_class(k, "active", n == name)

    def show_setup(self, active: bool) -> None:
        """Knopf 02 hervorheben, solange die Kopfzeile die Setup-Felder zeigt."""
        set_class(self.buttons["setup"], "active", active)

    def mark(self) -> None:
        """Zähler an 05 (Anzahl Prüfpunkte), ✓ an erledigten Kapiteln."""
        if not self.page.is_alive():
            return
        s = self.s
        done = {"datei": s.ifc is not None, "setup": s.ifc is not None, "regeln": s.df is not None,
                "ausgabe": s.result is not None and not s.stale}
        for name, badge in self.badges.items():
            if name == "pruefen":
                n = len(s.check_points) if s.ifc is not None else 0
                badge.set_text(str(n))
                badge.classes(replace="zaehler" if n else "hidden")
            else:
                badge.set_text("✓")
                badge.classes(replace="erledigt" if done.get(name) else "hidden")
