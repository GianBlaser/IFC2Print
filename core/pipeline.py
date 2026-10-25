"""Orchestrierung – die einzige Schnittstelle zwischen Oberfläche und Verarbeitung.

Zweck:   Fassade der Verarbeitung. Hier stehen die Schritte «Bauteile analysieren» und «Qualität wählen»;
         alles Übrige liegt in eigenen Modulen und bleibt unter ``pipeline.<name>`` erreichbar:
         core/generation.py (generate, mit core/voxels/elements.py und core/openings/fillers.py), core/output/result.py (Result, Downloads),
         core/analysis/check_points.py (Prüfpunkte), core/output/view_data.py (Viewer-Daten), core/output/model_info.py (Modell-Info),
         core/parts/roof.py (Dachteile).
Eingabe: IFC-Modell (core/ifc/model.py), Regelwerk, Massstab, Druckerprofil.
Ausgabe: Bauteiltabelle mit Aktion und Status (``analyse``), Voxelgrösse (``resolve_quality``), ``Result`` (``generate``).

Keine UI- oder Framework-Importe: dieselbe Logik läuft in der NiceGUI-App,
in den Skripten und in den Tests.
"""

from collections import defaultdict

import numpy as np
import pandas as pd
import trimesh

from config import AUTO_GRID_RATIO, MIN_WALL_MM, PACKAGE_GAP_MIN_MM, QUALITIES
from core.analysis import printability, surroundings
from core.analysis.ruleset import PRINTED_ACTIONS, Ruleset
from core.ifc.model import IfcModel
from core.output import report
from core.packages.grouping import group_plates
from core.packages.thickness import governing_thicknesses
from core.voxels import alignment
from core.voxels.shell import grid_limit      # hier nachgeschlagen: Tests ersetzen ``pipeline.grid_limit``

# Weitergereicht für Oberfläche, Skripte und Tests (``pipeline.<name>``)
from core.analysis.check_points import check_points, checklist, for_print, georeference_gaps
from core.generation import generate, scale_parameters
from core.output.model_info import model_overview
from core.output.report_data import report_context
from core.output.result import export_watertight, filename, Result
from core.output.view_data import (element_at_point, element_boxes, frame, ifc_preview, SELECTION_OFFSET_MM,
                                   selection_preview, status_preview, storey_order)
from core.parts.roof import roof_beam, roof_part, roof_zones
from core.voxels.elements import package_min_thickness

# Die Fassade: eigene Funktionen und alles, was weitergereicht wird (``pipeline.<name>``)
__all__ = [
    "analyse", "assign_packages", "alignment_angle", "resolve_quality", "elements_csv",
    "check_points", "checklist", "for_print", "georeference_gaps", "generate", "scale_parameters",
    "package_min_thickness", "model_overview", "report_context", "Result", "export_watertight", "filename", "roof_beam", "roof_part", "roof_zones",
    "SELECTION_OFFSET_MM", "element_at_point", "element_boxes", "frame", "ifc_preview", "selection_preview",
    "status_preview", "storey_order",
]


def analyse(ifc: IfcModel, ruleset: Ruleset, scale: int, profile: dict,
            exceptions: dict[str, str] | None = None, storeys: list[str] | None = None) -> pd.DataFrame:
    """Bauteile laden → Regel je Klasse → Umgebung und Ausreisser raus → Ausnahmen je Bauteil → Pakete → Druckbarkeit.

    ``exceptions``: GUID → Aktion; übersteuert Regel und Umgebung für einzelne Bauteile.
    ``storeys``: nur diese Geschosse drucken (None = alle) – Ausschnitte, v.a. bei 1:50.
    """
    df = ruleset.classify(ifc.building_elements, ifc.schema_id)
    outside = surroundings.is_surroundings(df)
    df.loc[outside, ["action", "category", "is_printed"]] = ["entfernen", "Umgebung", False]
    far = surroundings.outlier(df)
    df.loc[far, ["action", "category", "is_printed"]] = ["entfernen", "Ausreisser", False]
    for guid, action in (exceptions or {}).items():
        df.loc[df["guid"] == guid, ["action", "is_printed"]] = [action, action in PRINTED_ACTIONS]
    if storeys is not None:
        deselected = df["is_printed"] & ~df["storey"].isin(storeys)
        df.loc[deselected, ["action", "category", "is_printed"]] = ["entfernen", "Geschoss abgewählt", False]
    df = printability.check(assign_packages(ifc, df, scale, profile), scale, profile)
    df.loc[df["action"] == "band", "status"] = "druckbar"      # gedruckt als Band fester Dicke (core/voxels/band.py)
    return df


def assign_packages(ifc: IfcModel, df: pd.DataFrame, scale: int, profile: dict) -> pd.DataFrame:
    """Spalten ``package`` (Nummer, −1 = keins) und ``package_thickness_mm`` (real, massgebende Dicke:
    Paketdicke, bei stellenweise freistehenden Gliedern ihre Eigendicke) für gedruckte Platten.

    Ein Spalt zwischen zwei Schichten zählt zum Paket, solange er im Modell kleiner als
    die halbe Mindestwand ist – so fein lässt er sich ohnehin nicht drucken.
    """
    tolerance = max(PACKAGE_GAP_MIN_MM, 0.5 * profile.get("min_wall_mm", MIN_WALL_MM) * scale)
    candidates = df[df["is_printed"] & ~df["action"].isin(["fuellen", "band"]) & df["guid"].isin(list(ifc.plates))]
    plates = [ifc.plates[g] for g in candidates["guid"]]
    group_ids = group_plates(plates, tolerance)
    groups = defaultdict(list)
    for number, p in zip(group_ids, plates):
        groups[number].append(p)
    df = df.copy()
    df["package"] = -1
    df["package_thickness_mm"] = np.nan
    df.loc[candidates.index, "package"] = group_ids
    governing = {number: iter(governing_thicknesses(item_list)) for number, item_list in groups.items()}
    df.loc[candidates.index, "package_thickness_mm"] = [next(governing[number]) for number in group_ids]
    return df


def alignment_angle(ifc: IfcModel, df: pd.DataFrame) -> float:
    """Dominante Wandrichtung der gedruckten Bauteile (Grad); um diesen Winkel wird zurückgedreht."""
    meshes = [ifc.geometry[g].mesh(1) for g in df.loc[df["is_printed"], "guid"] if g in ifc.geometry]
    return alignment.main_angle(meshes)


def resolve_quality(quality: str, ifc: IfcModel, df: pd.DataFrame, scale: int,
                    angle: float = 0.0) -> tuple[float, str | None]:
    """Voxelgrösse zur Qualität; «auto» schätzt das Gitter bei 0.4 mm und weicht bei Bedarf auf 0.8 mm aus.

    Rückgabe: (Pitch in mm, Hinweis für den Bericht oder None).
    """
    if quality != "auto":
        return QUALITIES[quality], None
    fine, draft = QUALITIES["fein"], QUALITIES["entwurf"]
    guids = [g for g in df.loc[df["is_printed"], "guid"] if g in ifc.geometry]
    if not guids:
        return fine, None
    points = np.concatenate([ifc.geometry[g].verts for g in guids]) / scale
    extent = np.ptp(trimesh.transform_points(points, alignment.model_rotation(ifc, scale, angle)), axis=0)
    voxel = int(np.prod(np.ceil(extent / fine) + 4, dtype=np.float64))    # + Rand wie im Gitter
    limit_value = int(grid_limit() * AUTO_GRID_RATIO)
    if voxel > limit_value:
        return draft, (f"Qualität automatisch: entwurf ({draft} mm), weil das Gitter bei {fine} mm "
                       f"{voxel / 1e6:.0f} Mio. Voxel hätte (Grenze {limit_value / 1e6:.0f} Mio.).")
    return fine, f"Qualität automatisch: fein ({fine} mm, {voxel / 1e6:.0f} Mio. Voxel)."


def elements_csv(df: pd.DataFrame) -> bytes:
    """Bauteiltabelle als CSV für den Download."""
    return report.elements_csv(df)
