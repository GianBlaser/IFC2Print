"""Blatt «Verlauf»: die bisherigen Exporte als Tabelle.

Zweck:   Zeigt je Erzeugung eine Zeile mit Datei, Massstab, Einstellungen und Kennzahlen aus der Datenbank.
Eingabe: die Seite (page) mit Sitzung und Datenbank (export_runs)
Ausgabe: das Blatt «Verlauf» (Element self.sheet); content.refresh() lädt die Tabelle neu
"""

from nicegui import ui

from ui.texts import HISTORY_COLUMNS
from ui.widgets import sheet_frame, tag


class SheetHistory:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        with sheet_frame("Exportverlauf", "Verlauf", "sheet-xwide") as self.sheet:
            self.content()

    @ui.refreshable_method
    def content(self) -> None:
        runs = self.s.db.export_runs()
        if not runs:
            tag("p", "Noch keine Exporte.", "hint leer")
            return
        rows = [{**row, "connectors": "ja" if row.get("connectors") else "nein"} for row in runs]
        columns = [{"name": key, "label": label, "field": key, "align": "left"} for key, label in HISTORY_COLUMNS]
        ui.table(rows=rows, row_key="id", columns=columns).props("flat dense").classes("tabelle")
