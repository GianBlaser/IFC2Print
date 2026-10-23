"""Bauteile für das Voxelgitter vorbereiten: auswählen, Wandpakete auf ganze Voxel bringen, BuildingElements bauen.

Zweck:   Macht aus den gedruckten Zeilen der Bauteiltabelle die ``BuildingElement``-Objekte, die
         core.voxels.shell.voxelize ins Gitter schreibt. Wände und Decken werden paketweise auf ganze Voxel und die
         Mindestdicke gebracht (core/packages/grouping.py), übrige Bauteile bei Bedarf allseitig aufgedickt.
Eingabe: IFC-Modell, Bauteiltabelle (core.pipeline.analyse), Massstab, Drehmatrix, Voxelgrösse, Mindestwände.
Ausgabe: ``PreparedElements``: Bauteile, Geländer, Paket-Skalierungen, Füller-Modi, Geschoss-Z und Dachzonen.
"""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd
import trimesh

from core.analysis.ruleset import PRINTED_ACTIONS, ScaleParameters
from core.ifc.model import IfcModel
from core.openings.windows import fill_box
from core.packages.plates import is_wall
from core.packages.scaling import members_matrices, Scaling, scaling
from core.parts.roof import roof_name, roof_zones
from core.parts.storey_joints import storey_heights
from core.voxels.element_voxels import thickening_voxel
from core.voxels.grid import BuildingElement


@dataclass
class PackageScaling:
    """Wandpakete nach dem Skalieren (Schlüssel = Paketnummer aus der Spalte ``package``)."""
    scalings: dict[int, Scaling]                              # Skalierung je Paket
    boxes: list[tuple[Scaling, np.ndarray, np.ndarray]]        # (Skalierung, min, max) je Paket
    package_of: dict[str, int]                                          # GUID → Paketnummer
    matrix_of: dict[str, np.ndarray]                                    # GUID → Matrix, mit der das Bauteil skaliert wurde


@dataclass
class PreparedElements:
    """Alles, was ``generate`` nach dem Vorbereiten der Bauteile weiterreicht."""
    elements: list[BuildingElement]
    railing: list[tuple[tuple, trimesh.Trimesh]]        # (Zeile, Netz) der Geländer; erst nach dem Voxelisieren
    scaled: PackageScaling
    mode_per_guid: dict[str, str]                       # Öffnungsmodus je Füller (aus Ausnahme oder Regel «fuellen»)
    elevations: dict[str, float]                        # Welt-Z je Geschoss, reale mm
    zones: dict[str, tuple[np.ndarray, np.ndarray]]     # Dachzonen (siehe core/parts/roof.py)


def prepare_elements(ifc: IfcModel, df: pd.DataFrame, *, scale: int, rot_matrix: np.ndarray, pitch_mm: float,
                     min_wall_mm: float, wall_mm: float, exceptions: dict[str, str] | None = None) -> PreparedElements:
    """Gedruckte Bauteile → skalierte Wandpakete → ``BuildingElement`` (mit Dachteil, Gefälle und Öffnungen).

    ``min_wall_mm``: Mindestwand des Druckerprofils; ``wall_mm``: Mindestdicke der Wände aus dem Massstab-Regelwerk.
    Wirft ``ValueError``, wenn nichts Druckbares mit Geometrie übrig bleibt.
    """
    printed, railing, mode_per_guid = _select_printed(ifc, df, scale, rot_matrix, exceptions)
    scaled = _scale_packages(ifc, printed, rot_matrix, min_wall_mm, wall_mm, pitch_mm)
    elevations = dict(storey_heights(ifc.model, 1))          # Welt-Z je Geschoss, reale mm
    zones = roof_zones(ifc, [z for z, _ in printed], elevations)
    elements = []
    for z, mesh in printed:
        features = dict(storey=z.storey, roof=roof_name(ifc, z, elevations, zones), flatten=z.guid in ifc.slope,
                        guid=z.guid, voids=_voids(ifc, z.guid, scale, rot_matrix, scaled.matrix_of.get(z.guid)))
        elements.append(_element(z, mesh, features, z.guid in scaled.package_of, min_wall_mm, pitch_mm))
    if not elements:
        raise ValueError("Keine druckbaren Bauteile mit Geometrie – Regeln prüfen.")
    return PreparedElements(elements, railing, scaled, mode_per_guid, elevations, zones)


def _select_printed(ifc: IfcModel, df: pd.DataFrame, scale: int, rot_matrix: np.ndarray,
                    exceptions: dict[str, str] | None) -> tuple[list, list, dict[str, str]]:
    """Gedruckte Bauteile als (Zeile, Netz im Modellmass), Geländer getrennt, dazu der Öffnungsmodus je Füller.

    Fenster und Türen kennen nur diesen einen Mechanismus: Eine Ausnahme je Bauteil (``exceptions``,
    GUID → Aktion) schliesst die Öffnung («drucken») bzw. schneidet sie aus («nicht drucken»); die Regel
    «fuellen» wirkt bei ihnen wie «geschlossen», statt einen zweiten Füllquader zu erzeugen.
    Rückgabe: (Bauteile, Geländer, Modus je GUID).
    """
    filler = {f.guid for f in ifc.filler}
    mode_per_guid = {guid: "geschlossen" if action in PRINTED_ACTIONS else "ausgeschnitten"
                     for guid, action in (exceptions or {}).items() if guid in filler}
    mode_per_guid.update({z.guid: "geschlossen" for z in df[df["is_printed"] & (df["action"] == "fuellen")].itertuples()
                          if z.guid in filler and z.guid not in mode_per_guid})
    printed = [(z, ifc.geometry[z.guid].mesh(scale, rot_matrix))
               for z in df[df["is_printed"]].itertuples()
               if z.guid in ifc.geometry and not (z.action == "fuellen" and z.guid in filler)]
    railing = [(z, mesh) for z, mesh in printed if z.action == "band"]   # erst nach dem Voxelisieren
    return [(z, mesh) for z, mesh in printed if z.action != "band"], railing, mode_per_guid


def _scale_packages(ifc: IfcModel, printed: list, rot_matrix: np.ndarray, min_wall_mm: float, wall_mm: float,
                    pitch_mm: float) -> PackageScaling:
    """Wandpakete: alle Schichten gemeinsam nur entlang der Normale auf ganze Voxel bringen.

    Die Netze in ``printed`` werden dabei an Ort und Stelle verformt.
    """
    groups = defaultdict(list)
    for z, mesh in printed:
        if getattr(z, "package", -1) >= 0:
            groups[z.package].append((z, mesh))
    scaled = PackageScaling(scalings={}, boxes=[], package_of={}, matrix_of={})
    for number, members in groups.items():
        plates = [ifc.plates[z.guid].in_model(mesh.vertices, rot_matrix) for z, mesh in members]
        min_required = min_thickness(plates[0].normal_vector, min_wall_mm, wall_mm)
        s = scaled.scalings[number] = scaling(plates, min_required, pitch_mm)
        for (z, mesh), matrix in zip(members, members_matrices(plates, s, min_required, pitch_mm)):
            mesh.apply_transform(matrix)
            scaled.package_of[z.guid] = number
            scaled.matrix_of[z.guid] = matrix          # dieselbe Skalierung gilt für die Öffnungen des Bauteils
        points = np.concatenate([mesh.vertices for _, mesh in members])
        scaled.boxes.append((s, points.min(axis=0), points.max(axis=0)))
    return scaled


def _voids(ifc: IfcModel, guid: str, scale: int, rot_matrix: np.ndarray,
           package_matrix: np.ndarray | None) -> list[trimesh.Trimesh]:
    """Öffnungen ohne Füller (Treppenaugen, Schächte) im Modellmass; im Paket mit derselben Skalierung wie das Bauteil."""
    voids = [o.mesh(scale, rot_matrix) for o in ifc.voids.get(guid, [])]
    return voids if package_matrix is None else [o.apply_transform(package_matrix) for o in voids]


def _element(z: tuple, mesh: trimesh.Trimesh, features: dict, in_package: bool, min_wall_mm: float,
             pitch_mm: float) -> BuildingElement:
    """Ein Bauteil je nach Aktion: «fuellen» als Quader, «verdicken» allseitig aufgedickt, sonst so, wie es ist."""
    if z.action == "fuellen":
        return BuildingElement(fill_box(*mesh.bounds, min_wall_mm), **{**features, "voids": []})
    if z.action == "verdicken" and not in_package:   # Stützen, Träger u.ä.: bei Bedarf allseitig auf die Mindestwand aufdicken
        return BuildingElement(mesh, thickening_voxel(z.thickness_model_mm, min_wall_mm, pitch_mm), **features)
    return BuildingElement(mesh, **features)         # «behalten» wie im IFC; Pakete sind schon auf ganze Voxel skaliert


def min_thickness(normal_vector: np.ndarray, min_wall: float, wall_mm: float) -> float:
    """Wände (senkrechte Pakete) mindestens ``wall_mm`` (Massstab-Parameter), Decken und Dächer die Mindestwand.

    Das Druckerprofil bleibt die physikalische Grenze: wirksam ist immer das Maximum.
    """
    return max(wall_mm, min_wall) if is_wall(normal_vector) else min_wall


def package_min_thickness(ifc: IfcModel, guid: str, min_wall: float, wall_mm: float | None = None) -> float:
    """Mindestdicke für das Paket eines Bauteils – dieselbe Regel wie beim Erzeugen (Detailfeld)."""
    wall_mm = ScaleParameters.min_thickness_wall_mm if wall_mm is None else wall_mm
    p = ifc.plates.get(guid)
    return min_thickness(p.normal_vector, min_wall, wall_mm) if p is not None else min_wall
