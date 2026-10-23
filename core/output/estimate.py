"""Kalkulation: Filament, Kosten, Druckzeit (Schätzungen).

Eingabe: Volumen (cm³), Dichte, Preis, Modellhöhe und Layerhöhe
Ausgabe: Gramm, CHF, Stunden und der Rechenweg als Text (derivation)

Material- und Profilwerte kommen aus der Datenbank; die Faktoren in config.py
sind grobe Erfahrungswerte und als Schätzung zu deklarieren.
"""

from config import THROUGHPUT_CM3_H, LAYER_HEIGHT_MM, LAYER_CHANGE_H, VOLUME_FACTOR


def filament_grams(volume_cm3: float, density_g_cm3: float) -> float:
    return volume_cm3 * VOLUME_FACTOR * density_g_cm3


def cost_chf(grams: float, price_chf_kg: float) -> float:
    return grams / 1000 * price_chf_kg


def derivation(volume_cm3: float, height_mm: float, layer_height_mm: float, density_g_cm3: float,
               price_chf_kg: float) -> dict[str, tuple[list[str], float]]:
    """Rechenweg je Kennzahl mit den echten Werten: {Kennzahl: (Zeilen, Ergebnis)} – dieselben Formeln wie oben."""
    grams = filament_grams(volume_cm3, density_g_cm3)
    layer = height_mm / layer_height_mm
    extrusion = volume_cm3 * VOLUME_FACTOR / THROUGHPUT_CM3_H
    return {
        "Filament": ([f"Volumen {volume_cm3:.1f} cm³ × Faktor {VOLUME_FACTOR} × Dichte {density_g_cm3} g/cm³",
                      f"= {grams:.1f} g"], grams),
        "Druckzeit": ([f"{volume_cm3:.1f} cm³ × {VOLUME_FACTOR} ÷ {THROUGHPUT_CM3_H} cm³/h = {extrusion:.2f} h",
                       f"+ {layer:.0f} Layer ({height_mm:.0f} mm ÷ {layer_height_mm} mm) × {LAYER_CHANGE_H} h"
                       f" = {layer * LAYER_CHANGE_H:.2f} h",
                       f"= {extrusion + layer * LAYER_CHANGE_H:.1f} h"], print_time_hours(volume_cm3, height_mm, layer_height_mm)),
        "Kosten": ([f"{grams:.1f} g ÷ 1000 × {price_chf_kg:.2f} CHF/kg", f"= CHF {cost_chf(grams, price_chf_kg):.2f}"],
                   cost_chf(grams, price_chf_kg)),
    }


def print_time_hours(volume_cm3: float, height_mm: float,
                      layer_height_mm: float = LAYER_HEIGHT_MM) -> float:
    """Extrusionszeit + Zuschlag je Layer. ``height_mm`` = Höhe des gedruckten Modells."""
    layer = height_mm / layer_height_mm
    return volume_cm3 * VOLUME_FACTOR / THROUGHPUT_CM3_H + layer * LAYER_CHANGE_H
