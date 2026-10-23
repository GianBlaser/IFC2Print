"""Druckbett-Anordnung: die Teile druckfertig auf ein oder mehrere Betten verteilen.

Regal-Packing der Grundflächen: grösste Teile zuerst, Zeile für Zeile; ein Teil wird um 90° gedreht,
wenn es nur so aufs Bett passt, und kommt auf ein neues Bett, wenn das aktuelle voll ist.

Eingabe: Teile als Meshes (Modell-mm), Bettgrösse und Abstände [mm]
Ausgabe: Anordnung (``pack``) bzw. ein Mesh mit allen Teilen auf Z = 0 (``print_plate``)
"""

import numpy as np
import trimesh

from config import PRINT_BED_SPACING_MM, PRINT_GAP_MM


def pack(sizes: list[tuple[str, float, float]], width_mm: float, depth_mm: float,
           gap_mm: float) -> list[tuple[str, int, float, float, bool]]:
    """Regal-Packing der Grundflächen auf Druckbetten (breite × tiefe).

    ``sizes``: (Name, b, t) je Teil. Rückgabe (Name, Bett, x, y, gedreht).
    Grösste Teile zuerst; ein Teil wird um 90° gedreht, wenn es nur so aufs Bett passt.
    """
    def fits(b, t):                                  # 1e-6: Rundung beim Vergleich
        return b <= width_mm + 1e-6 and t <= depth_mm + 1e-6

    result, print_bed, x, y, row_t = [], 0, 0.0, 0.0, 0.0
    for name, b, t in sorted(sizes, key=lambda g: max(g[1], g[2]), reverse=True):
        rotated = not fits(b, t) and fits(t, b)
        if rotated:
            b, t = t, b
        if x + b > width_mm + 1e-6:                 # Zeile voll → neue Zeile
            x, y, row_t = 0.0, y + row_t + gap_mm, 0.0
        if y + t > depth_mm + 1e-6:                  # Bett voll → neues Bett
            print_bed, x, y, row_t = print_bed + 1, 0.0, 0.0, 0.0
        result.append((name, print_bed, x, y, rotated))
        x += b + gap_mm
        row_t = max(row_t, t)
    return result


def print_plate(parts: dict[str, trimesh.Trimesh], width_mm: float, depth_mm: float,
                gap_mm: float = PRINT_GAP_MM, print_bed_distance_mm: float = PRINT_BED_SPACING_MM) -> trimesh.Trimesh:
    """Alle Teile druckfertig (auf Z = 0) auf ein oder mehrere Betten verteilt."""
    layout = pack([(n, m.extents[0], m.extents[1]) for n, m in parts.items()],
                    width_mm, depth_mm, gap_mm)
    placed = []
    for name, print_bed, x, y, rotated in layout:
        m = parts[name].copy()
        if rotated:
            m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
        bottom = m.bounds[0]
        m.apply_translation([print_bed * (width_mm + print_bed_distance_mm) + x - bottom[0], y - bottom[1], -bottom[2]])
        placed.append(m)
    return trimesh.util.concatenate(placed)
