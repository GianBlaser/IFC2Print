"""Verlaufseintrag eines Erzeugungslaufs: Einstellungen und Kennzahlen für die Tabelle export_run.

Zweck:   Baut den Datenbankeintrag, der im Blatt «Verlauf» erscheint: welche Einstellungen galten (settings_of_run)
         und was dabei herauskam (figures_of_run). Gespeichert wird er von Session.generate (ui/state.py).
Eingabe: Einstellungen (ui.settings.Settings), Dateiname, Ergebnis (core.pipeline.Result), Bauteiltabelle
Ausgabe: dict mit den Spalten von export_run (das Datum setzt db.database selbst)
"""

import pandas as pd

from core import pipeline
from ui.settings import Settings


def settings_of_run(settings: Settings, filename: str) -> dict:
    """Einstellungen dieses Laufs, für den Verlauf."""
    return {"ifc_name": filename, "scale": settings.scale_denominator, "profile_id": settings.profile_data["id"],
            "ruleset_name": settings.ruleset_name, "mode": settings.quality, "windows": settings.windows,
            "doors": settings.doors, "connectors": int(settings.connectors)}


def figures_of_run(result: pipeline.Result, df: pd.DataFrame) -> dict:
    """Kennzahlen des Ergebnisses: Teile, gedruckte Bauteile, Filament, Druckzeit, Kosten."""
    return {"part_count": len(result.parts), "element_count": int(df["is_printed"].sum()),
            "filament_g": round(result.grams, 1),
            "time_h": round(result.time_h, 2), "cost_chf": round(result.cost_chf, 2)}
