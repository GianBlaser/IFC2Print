"""Dicke eines Pakets und freistehende Glieder.

Ein Paket besteht aus mehreren berührenden, parallelen Platten (z.B. Beton, Dämmung, Bekleidung).
Für die Druckbarkeit zählt die Dicke des ganzen Pakets – ausser ein Glied steht stellenweise allein
(``free_standing``), dann muss es dort selbst die Mindestdicke erreichen.

Eingabe: Liste von ``Plate`` (die Glieder eines Pakets)
Ausgabe: Paketdicke bzw. Intervall [mm], freistehend-Flag und massgebende Dicke je Glied
"""

import numpy as np

from config import PACKAGE_COVERED_RATIO
from core.packages.plates import Plate


def thickness(plates: list[Plate]) -> float:
    """Dicke eines Pakets: Ausdehnung aller Glieder entlang der Normale des ersten."""
    lo, hi = interval(plates)
    return hi - lo


def interval(plates: list[Plate]) -> tuple[float, float]:
    normal_vector = plates[0].normal_vector
    spans = [p.span(normal_vector) for p in plates]
    return min(s[0] for s in spans), max(s[1] for s in spans)


def free_standing(plates: list[Plate], fraction: float = PACKAGE_COVERED_RATIO) -> list[bool]:
    """Je Glied: True, wenn weniger als ``fraction`` seiner Fläche von anderen Gliedern abgedeckt ist.

    Ein solches Glied steht stellenweise allein (z.B. Innenwand, vor der nur auf einem Teil
    der Länge eine Schachtwand liegt) und muss dort selbst die Mindestdicke erreichen.

    Ein Randstreifen bis zur Paketdicke zählt nicht: Eine Fassadenschicht läuft an den Ecken
    um die Wand herum und deckt die Deckenstirn ab – dort liegt sie an Nachbarbauteilen an,
    steht also nicht frei, und ohne den Abzug fiele sie knapp unter ``fraction``.
    """
    axes = plates[0].axes[1:]
    margin = thickness(plates)
    rectangles = [np.array([p.span(a) for a in axes]) for p in plates]
    result = []
    for i, r in enumerate(rectangles):
        if np.prod(r[:, 1] - r[:, 0]) <= 0:
            result.append(True)
            continue
        inner_core = r + [margin, -margin]                     # ohne Randstreifen
        area = np.prod(inner_core[:, 1] - inner_core[:, 0])
        if (inner_core[:, 1] <= inner_core[:, 0]).any():         # nur Rand: liegt ganz an Nachbarn an
            result.append(False)
            continue
        capped = sum(np.prod(np.clip(np.minimum(inner_core[:, 1], q[:, 1]) - np.maximum(inner_core[:, 0], q[:, 0]), 0, None))
                      for j, q in enumerate(rectangles) if j != i)
        result.append(capped < fraction * area)
    return result


def governing_thicknesses(plates: list[Plate]) -> list[float]:
    """Je Glied die Dicke, die über die Druckbarkeit entscheidet: Paket- oder – freistehend – Eigendicke."""
    combined = thickness(plates)
    if len(plates) == 1:
        return [combined]
    return [float(np.ptp(p.span(plates[0].normal_vector))) if free else combined
            for p, free in zip(plates, free_standing(plates))]
