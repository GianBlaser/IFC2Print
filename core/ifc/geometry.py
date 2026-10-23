"""IFC-Geometrie: Bauteile mit allen Kernen triangulieren (ifcopenshell-Iterator).

Die Dreiecksnetze liegen in Weltkoordinaten (reale mm). Öffnungen werden NICHT boolesch abgezogen:
das scheitert an vielen Wänden. Sie werden robust im Voxelgitter ausgeschnitten – mit Fenster oder
Tür in core/openings/windows.py, ohne in core/voxels/shell.py (Aussparungen). Räume werden nie gebraucht und gar nicht
erst trianguliert. Netze mit nicht endlichen Koordinaten gelten als defekt und werden nur gemeldet.

Eingabe: geöffnetes IFC-Modell (optional nur bestimmte Elemente)
Ausgabe: ``Geometry`` je GUID und die GUIDs der defekten Netze
"""

import multiprocessing
from dataclasses import dataclass

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import trimesh


@dataclass(frozen=True)
class Geometry:
    """Trianguliertes Bauteil in Weltkoordinaten (reale mm)."""
    verts: np.ndarray   # (n, 3) float
    faces: np.ndarray   # (m, 3) int

    def mesh(self, scale: int, transform: np.ndarray | None = None) -> trimesh.Trimesh:
        """Bauteil als Trimesh im Modellmass [mm], optional gedreht (core.voxels.alignment)."""
        mesh = trimesh.Trimesh(self.verts / scale, self.faces, process=False)
        return mesh.apply_transform(transform) if transform is not None else mesh


def triangulate(model: ifcopenshell.file, only: list | None = None) -> tuple[dict[str, Geometry], set[str]]:
    """Trianguliert alle (oder nur die angegebenen) Elemente mit allen Kernen.

    Rückgabe: (Geometry je GUID, GUIDs mit nicht endlichen Koordinaten).
    """
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    # Öffnungen nicht boolesch abziehen: das scheitert an vielen Wänden. Ausgeschnitten wird
    # robust im Voxelgitter: mit Fenster/Tür in core/openings/windows.py, ohne in core/voxels/element_voxels.py (cut_voids).
    settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, True)
    # Räume werden nie gebraucht – gar nicht erst triangulieren
    options = {"include": only} if only else {"exclude": ["IfcSpace"]}
    result: dict[str, Geometry] = {}
    defective: set[str] = set()
    it = ifcopenshell.geom.iterator(settings, model, multiprocessing.cpu_count(), **options)
    if not it.initialize():
        return result, defective
    while True:
        shape = it.get()
        verts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3) * 1000.0  # m → mm
        faces = np.asarray(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
        if not np.isfinite(verts).all():          # defektes Netz: nie voxelisieren, in der Tabelle melden
            defective.add(shape.guid)
        elif len(faces):
            result[shape.guid] = Geometry(verts, faces)
        if not it.next():
            break
    return result, defective
