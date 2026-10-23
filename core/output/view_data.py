"""Daten für den 3D-Viewer: Vorschauen je Geschoss, Kamerarahmen und Anklicken von Bauteilen.

Zweck:   Bereitet das Modell so auf, wie es der Viewer braucht: ein GLB je Geschoss (nach Status, nach
         Geschossfarbe oder nur die Auswahl), die Boxen zum Anklicken und den Rahmen für die Kamera.
Eingabe: IFC-Modell, Bauteiltabelle (core.pipeline.analyse), Massstab und Ausrichtungswinkel.
Ausgabe: GLB-Bytes je Geschoss, Boxen je Bauteil, GUID des angeklickten Bauteils, Kamerarahmen.
"""

from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd
import trimesh

from core.ifc.model import IfcModel
from core.output import preview
from core.parts.storey_joints import storey_heights
from core.voxels import alignment


def frame(ifc: IfcModel, scale: int, angle: float = 0.0) -> tuple[np.ndarray, float, float]:
    """(Mitte unten, grösste Ausdehnung, Höhe) des (gedrehten) Modells im Modellmass [mm] – für die Kamera."""
    points = np.concatenate([g.verts for g in ifc.geometry.values()]) / scale
    points = trimesh.transform_points(points, alignment.model_rotation(ifc, scale, angle))
    lo, hi = points.min(axis=0), points.max(axis=0)
    return np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]), float((hi - lo).max()), float(hi[2] - lo[2])


def storey_order(ifc: IfcModel, df: pd.DataFrame) -> list[str]:
    """Geschossnamen der Tabelle, von unten nach oben.

    Gruppen ohne Geschoss (Grundstück, «unbekannt») kommen zuunterst: Im Viewer
    bleiben sie beim Auseinanderziehen am Boden statt zwischen die Geschosse zu rutschen.
    """
    heights = {name: z for name, z in storey_heights(ifc.model, 1)}
    return sorted(df["storey"].unique(), key=lambda g: (g in heights, heights.get(g, 0.0)))


def status_preview(ifc: IfcModel, df: pd.DataFrame, scale: int, angle: float = 0.0) -> dict[str, bytes]:
    """GLB je Geschoss für den Status-Modus.

    Gefärbt wird nur, was gedruckt wird (``is_printed``): nach Druckbarkeit. Nicht gedruckte Bauteile
    sind «ausgeschlossen» (neutraler Geist) – ihr Dickenstatus ist für den Druck ohne Belang.
    """
    rot_matrix = alignment.model_rotation(ifc, scale, angle)
    result = {}
    for storey in storey_order(ifc, df):
        meshes = [(ifc.geometry[z.guid].mesh(scale, rot_matrix), z.status if z.is_printed else "ausgeschlossen")
                  for z in df[df["storey"] == storey].itertuples() if z.guid in ifc.geometry]
        if meshes:
            result[storey] = preview.glb(meshes)
    return result


SELECTION_OFFSET_MM = 0.08      # Auswahl-Hülle liegt knapp über dem Bauteil (kein Flimmern gleicher Flächen)


def selection_preview(ifc: IfcModel, df: pd.DataFrame, guids: Iterable[str], scale: int,
                      angle: float = 0.0) -> dict[str, bytes]:
    """GLB je Geschoss nur mit den gewählten Bauteilen (Hervorhebung im Viewer)."""
    rot_matrix = alignment.model_rotation(ifc, scale, angle)
    storey = df.set_index("guid")["storey"]
    per_storey: dict[str, list] = {}
    for guid in guids:
        if guid in ifc.geometry and guid in storey.index:
            mesh = ifc.geometry[guid].mesh(scale, rot_matrix)
            mesh.vertices = mesh.vertices + mesh.vertex_normals * SELECTION_OFFSET_MM
            per_storey.setdefault(storey[guid], []).append((mesh, "selection"))
    return {g: preview.glb(meshes) for g, meshes in per_storey.items()}


def element_boxes(ifc: IfcModel, scale: int, angle: float = 0.0) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Achsenparallele Boxen (min, max) je Bauteil im Modellmass nach der Ausrichtung – zum Anklicken im Viewer."""
    rot_matrix = alignment.model_rotation(ifc, scale, angle)
    boxes = {}
    for guid, g in ifc.geometry.items():
        points = trimesh.transform_points(g.verts / scale, rot_matrix)
        boxes[guid] = (points.min(axis=0), points.max(axis=0))
    return boxes


def element_at_point(boxes: dict, df: pd.DataFrame, storey: str, point: Sequence[float], tolerance_mm: float = 0.3,
                     printed_only: bool = True) -> str | None:
    """GUID des Bauteils im Geschoss, auf dessen Oberfläche der Klickpunkt liegt (Modellmass).

    Mehrere Boxen können den Punkt enthalten (Wand und Decke): die kleinste gewinnt, sie ist die
    spezifischste. Liegt keine Box um den Punkt, zählt die nächste innerhalb der dreifachen Toleranz.
    """
    part = df[df["storey"] == storey]
    if printed_only:
        part = part[part["is_printed"]]
    p = np.asarray(point, dtype=float)
    inside, near = [], []
    for guid in part["guid"]:
        if guid not in boxes:
            continue
        lo, hi = boxes[guid]
        distance = float(np.linalg.norm(np.maximum(np.maximum(lo - p, p - hi), 0.0)))
        if distance <= tolerance_mm:
            inside.append((float(np.prod(np.maximum(hi - lo, 1e-6))), guid))
        elif distance <= 3 * tolerance_mm:
            near.append((distance, guid))
    if inside:
        return min(inside)[1]
    return min(near)[1] if near else None


def ifc_preview(ifc: IfcModel, df: pd.DataFrame, scale: int,
                angle: float = 0.0) -> dict[str, tuple[bytes | None, bytes | None]]:
    """GLB je Geschoss für den IFC-Modus: (Bauteile in der Geschossfarbe, defekte Bauteile rot).

    Getrennt, damit der Viewer ein Geschoss hervorheben kann, ohne die rote
    Defekt-Markierung zu verlieren.
    """
    rot_matrix = alignment.model_rotation(ifc, scale, angle)
    result = {}
    for rank, storey in enumerate(storey_order(ifc, df)):
        part = df[df["storey"] == storey]
        groups = []
        for defective in (False, True):
            meshes = [(ifc.geometry[z.guid].mesh(scale, rot_matrix), "defekt" if defective else preview.storey_color(rank))
                      for z in part[(part["geometry"] == "defekt") == defective].itertuples() if z.guid in ifc.geometry]
            groups.append(preview.glb(meshes) if meshes else None)
        if any(groups):
            result[storey] = tuple(groups)
    return result
