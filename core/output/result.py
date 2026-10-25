"""Ergebnis einer Modellerzeugung: Teile, Kennzahlen und alle Downloads (STL, ZIP, Druckplatte, PDF).

Zweck:   Bündelt, was ``generate`` liefert, und erzeugt daraus die Dateien für den Download.
Eingabe: Voxelgitter, Geschoss-Teile, Warnungen, Kennzahlen, Prüfpunkte, Überhänge, Steckverbinder und die
         Einstellungen des Laufs.
Ausgabe: ``Result`` mit STL-/ZIP-/PDF-Bytes und Vorschau; ``export_watertight`` und ``filename`` als Hilfen.
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
import pandas as pd
import trimesh

from config import VIEWER_MAX_FACES
from core.output import preview, report
from core.output.report_data import build_report_data
from core.parts.overhangs import Overhang
from core.parts.print_layout import print_plate
from core.voxels.grid import VoxelGrid


@dataclass
class Result:
    """Ergebnis einer Modellerzeugung inkl. aller Downloads."""
    voxel_grid: VoxelGrid = field(repr=False)
    parts: dict[str, trimesh.Trimesh] = field(repr=False)
    warnings: list[str]
    metrics: dict
    volume_cm3: float
    grams: float
    cost_chf: float
    time_h: float
    watertight: bool
    plug_pieces: dict[str, trimesh.Trimesh] | None = field(default=None, repr=False)   # Teile mit Steckverbindern
    overhang_marks: dict[str, trimesh.Trimesh] = field(default_factory=dict, repr=False)   # Stützstellen (rot im Viewer)
    # Eingaben der Kalkulation – für die Herleitung der Kennzahlen in der Oberfläche
    height_mm: float = 0.0
    layer_height_mm: float = 0.0
    density_g_cm3: float = 0.0
    price_chf_kg: float = 0.0
    # Für den PDF-Report (core/output/report_data.py)
    check_points: list[dict] = field(default_factory=list)      # für den Druck relevant, mit denen des Laufs
    overhangs: list[Overhang] = field(default_factory=list, repr=False)
    support_elements: dict[str, str] = field(default_factory=dict)   # Teil → Bauteil an der grössten Stützstelle
    connector_count: int = 0
    joint_count: int = 0
    pegs_per_part: dict[str, int] = field(default_factory=dict)      # Zapfen je Teil (das Teil unter der Fuge)
    clearance_mm: float = 0.0
    settings: dict = field(default_factory=dict)   # scale, pitch_mm, angle, windows, doors, profile, material

    @property
    def print_parts(self) -> dict[str, trimesh.Trimesh]:
        """Die Teile zum Drucken: mit Steckverbindern, falls geplant (sonst die reinen Hüllen)."""
        return self.plug_pieces or self.parts

    @property
    def combined(self) -> trimesh.Trimesh:
        """Das ganze Modell als Mehrkörper aus den Geschossteilen (sie berühren sich nur an den Fugen).

        Früher wurde dafür das ganze Gitter neu vernetzt – beim NEST-Modell mit 10.8 GB Speicherspitze.
        """
        return trimesh.util.concatenate(list(self.parts.values()))

    @cached_property
    def leaky_parts(self) -> list[str]:
        """Druckteile, die nach dem STL-Export nicht wasserdicht sind (für den PDF-Report)."""
        return [name for name, mesh in self.print_parts.items() if not export_watertight(mesh)]

    def stl(self) -> bytes:
        """Das ganze Modell als eine STL-Datei."""
        return self.combined.export(file_type="stl")

    def stl_zip(self, base_name: str) -> bytes:
        """Alle Druckteile als STL-Dateien in einem ZIP (``<base_name>_<Teilname>.stl``)."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, mesh in self.print_parts.items():
                zf.writestr(f"{base_name}_{filename(name)}.stl", mesh.export(file_type="stl"))
        return buffer.getvalue()

    def stl_plate(self, profile: dict) -> bytes:
        """Alle Druckteile nebeneinander auf einer Druckplatte in der Bettgrösse des Profils (STL)."""
        plate = print_plate(self.print_parts, profile["build_volume_x_mm"], profile["build_volume_y_mm"])
        return plate.export(file_type="stl")

    def report_pdf(self, df: pd.DataFrame, context: dict) -> bytes:
        """Übergabeblatt als PDF (core/output/report.py); ``context`` von ``report_data.report_context``."""
        return report.report_pdf(build_report_data(df, context, self, self.check_points))

    @cached_property
    def preview(self) -> dict[str, bytes]:
        """GLB je Druckteil für den Viewer (auf VIEWER_MAX_FACES reduziert); wird beim ersten Zugriff berechnet."""
        return preview.stl_preview(self.print_parts, VIEWER_MAX_FACES, self.overhang_marks)


def export_watertight(mesh: trimesh.Trimesh) -> bool:
    """True, wenn das Teil auch nach dem STL-Export (float32) noch wasserdicht ist.

    Geprüft wird die Datei, wie sie der Slicer liest – nicht das Netz im Speicher. So fällt auf,
    wenn Koordinaten zu gross für float32 sind (siehe core.ifc.model, Versatz).
    Gleichwertig zum Neuladen, aber ohne Export: Das STL bleibt dicht, solange keine zwei
    verschiedenen Punkte in float32 zusammenfallen – dann hat die Datei dieselbe Topologie wie das Netz.
    """
    if not mesh.is_watertight:
        return False
    points = np.unique(mesh.vertices, axis=0)
    return len(np.unique(points.astype(np.float32), axis=0)) == len(points)


def filename(text: str) -> str:
    """Macht einen Geschossnamen dateisystemtauglich."""
    return re.sub(r"[^\w.-]+", "_", text).strip("_") or "teil"
