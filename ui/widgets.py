"""Kleine Bausteine der Oberfläche, die mehrere Blätter gemeinsam brauchen.

Zweck:   HTML-Elemente mit Text (tag), Knöpfe (button), Klassen schalten (set_class), Blattrahmen (sheet_frame),
         gemerkte Ansicht (saved, remember), Zahlen- und Geschossnamen sowie die Aktionsknöpfe einer Regel.
Eingabe: Texte, CSS-Klassen und Klick-Funktionen der aufrufenden Blätter
Ausgabe: NiceGUI-Elemente, die im aktuellen Aufbau-Kontext (with-Block) entstehen
"""

from collections.abc import Callable
from typing import Any

from nicegui import app, ui
from nicegui.elements.mixins.text_element import TextElement

from core.analysis.ruleset import ACTIONS
from ui.texts import ACTION_SHORT


def mm_text(mm: float) -> str:
    """92 · 60.5 · 210 – ab 100 mm ganze Millimeter, sonst eine Stelle (ohne «.0»)."""
    return f"{mm:.0f}" if mm >= 100 else f"{mm:.1f}".removesuffix(".0")


def saved(key: str, default: Any = None) -> Any:
    """Wert aus app.storage.user (Ansicht merken); ohne Speicher den Standard."""
    try:
        return app.storage.user.get(key, default)
    except RuntimeError:
        return default


def remember(key: str, value: Any) -> None:
    """Wert in app.storage.user merken; ohne Speicher passiert nichts."""
    try:
        app.storage.user[key] = value
    except RuntimeError:
        pass


def set_class(element: ui.element, css_class: str, enabled: bool) -> None:
    """CSS-Klasse am Element ein- (enabled) oder ausschalten."""
    element.classes(add=css_class if enabled else "", remove="" if enabled else css_class)


def storey_label(name: str) -> str:
    """Anzeigename eines Geschosses: das Grundstück heisst «Parzelle»."""
    return "Parzelle" if "grundstück" in name.lower() else name


def tag(name: str, text: str = "", css_classes: str = "") -> TextElement:
    """Ein beliebiges HTML-Element mit Text (für das Markup des Designs)."""
    return TextElement(tag=name, text=text).classes(css_classes)


def button(css_classes: str, on_click: Callable, bold: str = "", text: str = "") -> ui.element:
    """HTML-Knopf; ``bold`` steht fett voran (z.B. die Nummer in der Leiste), ``text`` dahinter."""
    with ui.element("button").classes(css_classes).on("click", on_click) as b:
        if bold:
            tag("b", bold)
        if text:
            tag("span", text)
    return b


def sheet_frame(title: str, seq_number: str, css_class: str = "") -> ui.element:
    """Rahmen eines Blattes: Kopf mit Titel und Nummer (z.B. «01 / 05»); der Inhalt kommt danach hinein."""
    with ui.element("section").classes(f"sheet {css_class}") as sheet:
        with ui.element("div").classes("sheet-head"):
            tag("h2", title)
            tag("span", seq_number)
    return sheet


def action_buttons(ifc_class: str, active: str, on_pick: Callable, category: str = "Sonstiges") -> None:
    """Die fünf Aktionsknöpfe einer Regel (behalten … entfernen); ``active`` ist hervorgehoben.

    ``on_pick(ifc_class, action, category)`` wird beim Klick aufgerufen."""
    with ui.element("div").classes("regel-aktionen"):
        for action in ACTIONS:
            button("active" if action == active else "", lambda a=action: on_pick(ifc_class, a, category),
                   text=ACTION_SHORT[action]).props(f"data-aktion={action}").mark(f"regel-{ifc_class}-{action}")
