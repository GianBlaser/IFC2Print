"""Kleine Bausteine der Oberfläche, die mehrere Blätter gemeinsam brauchen.

Zweck:   HTML-Elemente mit Text (tag), Knöpfe (button), Klassen schalten (set_class), Blattrahmen (sheet_frame),
         Hover-Popups (popup), gemerkte Ansicht (saved, remember), Zahlen- und Geschossnamen sowie die
         Radio-Punkte einer Regel.
Eingabe: Texte, CSS-Klassen und Klick-Funktionen der aufrufenden Blätter
Ausgabe: NiceGUI-Elemente, die im aktuellen Aufbau-Kontext (with-Block) entstehen
"""

from collections.abc import Callable
from typing import Any

from nicegui import app, ui
from nicegui.elements.mixins.text_element import TextElement

from core.analysis.ruleset import ACTIONS


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


def popup(text: str = "") -> ui.tooltip:
    """Hover-Popup im Stil der Oberfläche (12 px rechts / 16 px unter dem Element, ohne Verzögerung).

    Mehrzeiliger Text: die erste Zeile ist fett. Ohne Text bleibt das Popup leer und nimmt Inhalt im with-Block auf."""
    tip = ui.tooltip().classes("popup").props('anchor="bottom left" self="top left" :offset="[12, 16]"')
    if text:
        first, _, rest = text.partition("\n")
        with tip:
            if rest:
                tag("b", first)
                tag("div", rest)
            else:
                tag("span", first)
    return tip


def sheet_frame(title: str, css_class: str = "", aside: str = "") -> ui.element:
    """Rahmen eines Blattes: Kopf mit Titel und optional grauem Text rechts; der Inhalt kommt danach hinein."""
    with ui.element("section").classes(f"sheet {css_class}") as sheet:
        with ui.element("div").classes("sheet-head"):
            tag("h2", title)
            if aside:
                tag("span", aside)
    return sheet


def radio_buttons(ifc_class: str, active: str, on_pick: Callable, category: str = "Sonstiges",
                  inherited: bool = False) -> None:
    """Je Aktion ein Radio-Punkt (behalten … entfernen); ``active`` ist gewählt, gestrichelt bei geerbter Regel.

    ``on_pick(ifc_class, action, category)`` wird beim Klick aufgerufen. Die Spalte nennt die Aktion; ein Popup je
    Punkt (5 je Zeile) würde die Liste bei jedem Neuzeichnen stark verlangsamen, darum nur aria-label."""
    for action in ACTIONS:
        state = "" if action != active else " geerbt" if inherited else " eigen"
        with ui.element("div").classes("radio-zelle"):
            with button("radio" + state, lambda a=action: on_pick(ifc_class, a, category)).props(
                    f'aria-label="{ifc_class}: {action}"').mark(f"regel-{ifc_class}-{action}"):
                tag("i")
