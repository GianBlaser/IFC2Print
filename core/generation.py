"""Erzeugung: aus der Bauteiltabelle die geschossweise geteilte, wasserdichte Voxel-Hülle machen.

Zweck:   ``generate`` bereitet die Bauteile vor (core/voxels/elements.py), voxelisiert sie, setzt Geländer, Fenster und
         Türen, teilt das Gitter in Geschoss- und Dachteile, prüft die Überhänge je Teil, plant optional
         Steckverbinder und rechnet Kennzahlen.
Eingabe: IFC-Modell, Bauteiltabelle, Massstab, Voxelgrösse, Druckerprofil, Material und Öffnungsmodi.
Ausgabe: ``Result`` (core/output/result.py) mit Teilen, Warnungen, Kennzahlen und Downloads.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
import trimesh

from config import CLEARANCE_MM
from core.analysis.check_points import check_points, for_print, run_points, sentence
from core.analysis.ruleset import ScaleParameters
from core.connectors.geometry import apply_connectors
from core.connectors.planning import plan_connectors
from core.ifc.model import IfcModel
from core.openings.fillers import collect_openings, insert_openings
from core.openings.windows import check_mode
from core.output import estimate
from core.output.result import export_watertight, Result
from core.output.view_data import element_at_point, element_boxes
from core.parts import partitioning
from core.parts.overhangs import mark, message, Overhang, overhangs, summary
from core.parts.storey_joints import storey_heights
from core.voxels import alignment, band
from core.voxels.elements import prepare_elements, PreparedElements
from core.voxels.grid import BuildingElement, VoxelGrid
from core.voxels.shell import voxelize


@dataclass(frozen=True)
class _Run:
    """Ein Erzeugungslauf: die Eingaben von ``generate``, die mehrere Schritte brauchen (statt zwölf Parameter)."""
    ifc: IfcModel
    scale: int
    pitch_mm: float
    rot_matrix: np.ndarray                          # dreht das Modell um ``angle`` zurück (core/voxels/alignment.py)
    profile: dict
    material: dict
    angle: float
    windows: str
    doors: str
    connectors: bool
    parameter: ScaleParameters
    report: Callable[[str, float], None]            # meldet (Phase, Anteil 0..1) an den Aufrufer

    @property
    def min_wall_mm(self) -> float:
        """Mindestwand des Druckerprofils."""
        return self.profile["min_wall_mm"]


def generate(ifc: IfcModel, df: pd.DataFrame, *, scale: int, pitch_mm: float,
             profile: dict, material: dict, angle: float = 0.0,
             windows: str = "geschlossen", doors: str = "geschlossen",
             exceptions: dict[str, str] | None = None, connectors: bool = False,
             progress: Callable[[str, float], None] | None = None,
             parameter: ScaleParameters | None = None) -> Result:
    """Erzeugt die geschossweise geteilte, wasserdichte Voxel-Hülle mit Kennzahlen.

    ``parameter``: Regelwerk-Parameter des Massstabs (Mindestdicke Wand, Laibung, Steckverbinder);
    ohne Angabe die Standardwerte des Massstabs 1:``scale``.
    ``angle``: Drehung gegen die Treppenstufen schräger Wände (siehe alignment_angle).
    ``windows`` / ``doors``: geschlossen | ausgeschnitten | vertieft (core/openings/windows.py); getrennt
    je Öffnungsart, wirken über die ganze Dicke des Wandpakets. Öffnungen ohne Fenster
    oder Tür (Sanitär, Schächte) bleiben, wie sie im IFC sind.
    ``exceptions``: GUID → Aktion je Bauteil (für Fenster und Türen siehe core/voxels/elements.py).
    ``progress(phase, fraction)`` meldet den Gesamtfortschritt 0..1.
    """
    mode_per_variant = {"windows": check_mode(windows), "doors": check_mode(doors)}
    report_progress = _progress_reporter(progress)
    report_progress("Bauteile vorbereiten", 0.0)          # sofort melden: die Vorbereitung dauert bei grossen Modellen
    parameter = parameter or scale_parameters(scale)
    run = _Run(ifc, scale, pitch_mm, alignment.model_rotation(ifc, scale, angle), profile, material, angle,
               windows, doors, connectors, parameter, report_progress)
    prep = prepare_elements(ifc, df, scale=scale, rot_matrix=run.rot_matrix, pitch_mm=pitch_mm,
                            min_wall_mm=run.min_wall_mm, wall_mm=parameter.min_thickness_wall_mm, exceptions=exceptions)
    grid, opening_count, warnings = _build_grid(run, prep, mode_per_variant)
    parts, partition = _split_into_parts(run, df, grid)
    report_progress("Überhänge prüfen", 1.0)
    supports = overhangs(partition.labels, partition.mesh_names, grid.pitch, grid.origin)
    analysis_points, element_points = for_print(check_points(ifc, df)), _element_points(df, prep.elements)
    overhang_notes, support_elements = _overhang_notes(run, df, supports)
    warnings = ([sentence(p) for p in analysis_points] + grid.warnings + warnings + list(partition.warnings)
                + [sentence(p) for p in element_points] + overhang_notes)
    report_progress("Fertig", 1.0)

    leaky = [name for name, m in parts.items() if not export_watertight(m)]
    if leaky:
        warnings.append("Nach dem STL-Export nicht wasserdicht: " + ", ".join(leaky) + " – im Slicer prüfen.")
    plug, connector_warnings, connector_figures = _connect_parts(run, grid, partition, parts)
    figures = _estimate(run, grid, parts)
    marks = {o.name: m for o in supports if (m := mark(o, grid.pitch, grid.origin)) is not None}
    return Result(voxel_grid=grid, parts=parts, warnings=warnings + connector_warnings,
                  metrics=_metrics(run, df, prep, parts, opening_count, figures, supports),
                  watertight=not leaky, plug_pieces=plug, overhang_marks=marks, **figures,
                  check_points=analysis_points + element_points, overhangs=supports,
                  support_elements=support_elements, settings=_settings(run), **connector_figures)


def scale_parameters(scale: int) -> ScaleParameters:
    """Standard-Parameter des Massstabs 1:``scale``; andere Massstäbe (Skripte, Tests) erhalten die 1:200-Werte."""
    try:
        return ScaleParameters.default(f"1:{scale}")
    except ValueError:
        return ScaleParameters()


def _progress_reporter(progress: Callable[[str, float], None] | None) -> Callable[[str, float], None]:
    """Meldefunktion, die ohne ``progress`` nichts tut (spart die Prüfung bei jeder Meldung)."""
    def report_progress(phase: str, fraction: float) -> None:
        if progress:
            progress(phase, fraction)
    return report_progress


def _build_grid(run: _Run, prep: PreparedElements,
                mode_per_variant: dict[str, str]) -> tuple[VoxelGrid, int, list[str]]:
    """Bauteile voxelisieren, dann Geländer und Öffnungen einsetzen; (Gitter, Anzahl wirksamer Öffnungen, Warnungen)."""
    warnings: list[str] = []
    run.report("Fenster und Türen zuordnen", 0.03)
    openings = collect_openings(run.ifc, run.scale, run.rot_matrix, prep.scaled,
                                max(run.parameter.min_thickness_wall_mm, run.min_wall_mm), run.pitch_mm, warnings)
    grid = voxelize(prep.elements, run.pitch_mm, run.scale,
                    progress=lambda i, n: run.report("Voxelisieren", 0.05 + 0.55 * i / n))
    if prep.railing:
        run.report("Geländer als Bänder", 0.6)
        warnings += band.place_railing_bands(run.ifc, grid, prep.railing, run.parameter, prep.elevations, prep.zones)
    run.report("Fenster und Türen einsetzen", 0.6)
    opening_count = insert_openings(grid, openings, mode_per_variant, prep.mode_per_guid, run.min_wall_mm, run.parameter)
    return grid, opening_count, warnings


def _split_into_parts(run: _Run, df: pd.DataFrame,
                      grid: VoxelGrid) -> tuple[dict[str, trimesh.Trimesh], partitioning.Partition]:
    """Gitter in Geschoss- und Dachteile aufteilen und vernetzen; (Teile, Aufteilung)."""
    run.report("Geschosse und Dächer aufteilen", 0.62)
    # Nur Geschosse mit gedruckten Bauteilen schneiden: abgewählte oder leere Geschosse lägen ausserhalb
    # des Gitters und ergäben hauchdünne Zusatzteile.
    printed_storeys = set(df.loc[df["is_printed"], "storey"])
    heights = [(name, z) for name, z in storey_heights(run.ifc.model, run.scale) if name in printed_storeys]
    partition = partitioning.partition_grid(grid, heights, run.scale, grid.floor_plans, grid.roof, grid.roof_names)
    parts = partitioning.mesh_pieces(
        grid, partition, progress=lambda name, i, n: run.report(f"Vernetzen «{name}»", 0.65 + 0.35 * i / n))
    return parts, partition


def _element_points(df: pd.DataFrame, elements: list[BuildingElement]) -> list[dict]:
    """Prüfpunkte zu Öffnungen ohne Füller und zu eben gemachten Decken (Gefälle), je IFC-Klasse gezählt."""
    ifc_class = dict(zip(df["guid"], df["ifc_class"]))
    cut, flattened = Counter(), Counter()
    for b in elements:
        cut[ifc_class.get(b.guid, "ohne Klasse")] += len(b.voids)
        flattened[ifc_class.get(b.guid, "ohne Klasse")] += b.flatten
    return run_points(+cut, +flattened)                       # «+» lässt die Klassen ohne Fall weg


def _overhang_notes(run: _Run, df: pd.DataFrame, supports: list[Overhang]) -> tuple[list[str], dict[str, str]]:
    """Je Teil mit Stützbedarf eine Meldung samt Bauteil an der grössten Stelle (core/parts/overhangs.py);
    (Meldungen, Teil → Name dieses Bauteils)."""
    relevant = [o for o in supports if o.relevant]
    if not relevant:
        return ([text] if (text := summary(supports)) else []), {}
    boxes = element_boxes(run.ifc, run.scale, run.angle)      # nur bei Stützbedarf: kostet bei grossen Modellen ~1 s
    notes, elements = [], {}
    for o in relevant:
        guid = element_at_point(boxes, df, None, o.center, tolerance_mm=run.pitch_mm)
        row = df[df["guid"] == guid].iloc[0] if guid else None
        notes.append(message(o, None if row is None else f"{row['ifc_class']} «{row['name']}»"))
        if row is not None:
            elements[o.name] = row["name"] or row["ifc_class"]
    return notes, elements


def _connect_parts(run: _Run, grid: VoxelGrid, partition: partitioning.Partition, parts: dict[str, trimesh.Trimesh]
                   ) -> tuple[dict[str, trimesh.Trimesh] | None, list[str], dict]:
    """Steckverbinder planen und einbauen; (Teile mit Steckverbindern oder None, Warnungen,
    Anzahlen als Felder von ``Result``)."""
    if not run.connectors:
        return None, [], {}
    if not run.parameter.connectors_allowed:
        return None, [f"Steckverbinder bei {run.parameter.ruleset_name} nicht möglich (Wände zu dünn für die Zapfen)."], {}
    run.report("Steckverbinder", 1.0)
    clearance = run.profile.get("clearance_mm", CLEARANCE_MM)   # Passungsspiel aus dem Druckerprofil, sonst config.py
    plan, warn_plan = plan_connectors(grid, partition, clearance)
    plug, warn_geo = apply_connectors(parts, partition.mesh_names, plan, clearance)
    joints = len({(v.bottom, v.top) for v in plan})
    figures = dict(connector_count=len(plan), joint_count=joints, clearance_mm=clearance,
                   pegs_per_part=dict(Counter(partition.mesh_names[v.bottom] for v in plan)))   # Zapfen am Teil unten
    return (plug, warn_plan + warn_geo + [f"Steckverbinder: {len(plan)} an {joints} Fugen (Spiel {clearance:.2f} mm)."],
            figures)


def _settings(run: _Run) -> dict:
    """Einstellungen des Laufs für den PDF-Report."""
    return dict(scale=run.scale, pitch_mm=run.pitch_mm, angle=run.angle, windows=run.windows, doors=run.doors,
                profile=dict(run.profile), material=dict(run.material))


def _estimate(run: _Run, grid: VoxelGrid, parts: dict[str, trimesh.Trimesh]) -> dict:
    """Volumen, Filament, Kosten und Druckzeit der Teile – als Felder von ``Result`` (core/output/estimate.py)."""
    volume_cm3 = sum(m.volume for m in parts.values()) / 1000                   # mm³ → cm³
    density, price = run.material["density_g_cm3"], run.material["price_chf_kg"]
    grams = estimate.filament_grams(volume_cm3, density)
    height_mm = grid.matrix.shape[2] * run.pitch_mm
    layer_height = run.profile["layer_height_mm"]
    return dict(volume_cm3=volume_cm3, grams=grams, cost_chf=estimate.cost_chf(grams, price),
                time_h=estimate.print_time_hours(volume_cm3, height_mm, layer_height),
                height_mm=height_mm, layer_height_mm=layer_height, density_g_cm3=density, price_chf_kg=price)


def _metrics(run: _Run, df: pd.DataFrame, prep: PreparedElements, parts: dict[str, trimesh.Trimesh],
             opening_count: int, figures: dict, supports: list[Overhang]) -> dict:
    """Kennzahlen für Oberfläche und Bericht, in der Reihenfolge der Anzeige."""
    return {
        "Schema": run.ifc.schema,
        "Massstab": f"1:{run.scale}",
        "Profil": run.profile["name"],
        "Material": run.material["name"],
        "Voxel-Pitch (mm)": f"{run.pitch_mm:.2f}",
        "Ausrichtung (°)": f"{run.angle:.1f}",
        "Fenster": run.windows,
        "Türen": run.doors,
        "Öffnungen": opening_count,
        "Bauteile": len(df),
        "Gedruckt": int(df["is_printed"].sum()),
        "Verdickt": sum(1 for b in prep.elements if b.thickening > 0) + sum(c.thickened for c in prep.scaled.scalings.values()),
        "Gefüllt": int((df["is_printed"] & (df["action"] == "fuellen")).sum()),
        "Geschoss-Teile": len(parts),
        "Filament (g, Schätzung)": f"{figures['grams']:.1f}",
        "Kosten (CHF, Schätzung)": f"{figures['cost_chf']:.2f}",
        "Druckzeit (h, Schätzung)": f"{figures['time_h']:.1f}",
        "Stützfläche (cm²)": f"{sum(o.support_mm2 for o in supports if o.relevant) / 100:.1f}",
    }
