"""Druckbett im 3D-Viewer: feines Gitter und Bauraum-Rahmen unter dem Modell.

Zweck:   Zeichnet in die Szene ein 10-mm-Raster über etwa den doppelten Bauraum und den Bauraum des Druckers als
         orangen Rahmen. Das Raster nimmt die Farbe des Themes (hell oder dunkel) an.
Eingabe: die NiceGUI-Szene (ui.scene); Mittelpunkt unten (x, y, z) des Modells und Bauraum (x, y) in mm
Ausgabe: Linien in der Szene; draw() ersetzt die alten Linien, set_theme() färbt das Raster um
"""

import math

from nicegui import ui

GRID_COLOR = {"light": "#BDB6A8", "dark": "#3A404A"}
BUILD_VOLUME_COLOR = "#FF6B2C"
GRID_SPACING_MM = 10.0


class PrintBed:
    def __init__(self, scene: ui.scene):
        self.scene = scene
        self._bed_lines: list = []          # alle Linien des Druckbetts
        self._grid_lines: list = []          # davon die Rasterlinien (Themefarbe)

    def draw(self, x: float, y: float, z: float, print_bed_mm: tuple[float, float]) -> None:
        """Feines Gitter (10-mm-Raster) über ~2× den Bauraum, Bauraum selbst als Rahmen."""
        for obj in self._bed_lines:
            obj.delete()
        half = math.ceil(max(print_bed_mm) / GRID_SPACING_MM) * GRID_SPACING_MM   # ≈ 2× Bauraum gesamt
        steps = int(half / GRID_SPACING_MM)
        tick_positions = [i * GRID_SPACING_MM for i in range(-steps, steps + 1)]
        bx, by = print_bed_mm[0] / 2, print_bed_mm[1] / 2
        corners = [[x - bx, y - by, z], [x + bx, y - by, z], [x + bx, y + by, z], [x - bx, y + by, z]]
        with self.scene:
            lines = [self.scene.line([x + s, y - half, z], [x + s, y + half, z]) for s in tick_positions]
            lines += [self.scene.line([x - half, y + s, z], [x + half, y + s, z]) for s in tick_positions]
            frame = [self.scene.line(a, b).material(BUILD_VOLUME_COLOR)
                     for a, b in zip(corners, corners[1:] + corners[:1])]
        self._grid_lines, self._bed_lines = lines, lines + frame

    def set_theme(self, theme: str) -> None:
        """Rasterfarbe für ``"light"`` oder ``"dark"``."""
        for line_item in self._grid_lines:
            line_item.material(GRID_COLOR[theme], 0.6)
