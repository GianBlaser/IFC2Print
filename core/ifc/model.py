"""IFC-Import: Bauteiltabelle und Geometrie.

Die Geometrie wird genau EINMAL trianguliert (ifcopenshell-Iterator, alle Kerne)
und je GUID zwischengespeichert. Analyse, Viewer und Hüllenerzeugung greifen auf
diesen Cache zu, statt das Modell jedes Mal neu zu triangulieren.
Alle Längen sind reale Millimeter (Massstab 1:1); skaliert wird erst beim Verbraucher.

Georeferenzierte Modelle (z.B. LV95, x ≈ 2 600 000 m) werden beim Einlesen im Grundriss
zum Ursprung verschoben (``offset_mm``): STL und GLB speichern float32, das bei solchen
Koordinaten nur noch 1 mm auflöst – feiner als ein Voxel wäre nichts mehr dicht. Die Höhe
bleibt im Weltsystem; Geschoss-Z und Koten stimmen dadurch weiter direkt.

Die Einzelteile stehen in eigenen Modulen: core/ifc/geometry.py (Triangulieren),
core/ifc/assignment.py (Klassenfamilie, Geschoss, Layer), core/ifc/openings.py (Füller und Öffnungen),
core/ifc/table.py (Bauteiltabelle). ``IfcModel`` hält sie zusammen und rechnet jedes Ergebnis nur einmal.

Eingabe: IFC-Datei (Pfad oder Bytes)
Ausgabe: ``IfcModel`` mit Geometrie, Bauteiltabelle, Platten, Gefälle, Füllern und Öffnungen
"""

from functools import cached_property
from pathlib import Path

import ifcopenshell
import numpy as np
import pandas as pd

from config import SLOPE_DEG, OFFSET_THRESHOLD_MM, OFFSET_GRID_MM
from core.ifc.assignment import class_family, is_element
from core.ifc.geometry import Geometry, triangulate
from core.ifc.openings import Filler, find_fillers, find_voids
from core.ifc.table import element_table
from core.packages.plates import has_slope, Plate, plate, PLATE_CLASSES


class IfcModel:
    """Kapselt eine geöffnete IFC-Datei."""

    def __init__(self, model: ifcopenshell.file):
        self.model = model
        self.schema = model.schema
        self.schema_id = model.schema_identifier      # z.B. IFC4X3_ADD2 – für die Vererbungskette
        self._offset = np.zeros(3)
        self.defective: set[str] = set()                   # GUIDs mit nicht endlichen Koordinaten

    @classmethod
    def open_file(cls, file_path: str | Path) -> "IfcModel":
        return cls(ifcopenshell.open(str(file_path)))

    @classmethod
    def from_bytes(cls, data: bytes) -> "IfcModel":
        """Öffnet einen Upload direkt aus dem Speicher (keine Temp-Datei)."""
        return cls(ifcopenshell.file.from_string(data.decode("utf-8", errors="replace")))

    # --- Geometrie --------------------------------------------------------

    @cached_property
    def _raw(self) -> dict[str, Geometry]:
        """Alle triangulierten Elemente samt Aussparungen, im Grundriss um ``offset_mm`` verschoben."""
        raw = self._triangulate()
        if raw:
            lo = np.min([g.verts.min(axis=0) for g in raw.values()], axis=0)
            hi = np.max([g.verts.max(axis=0) for g in raw.values()], axis=0)
            if np.abs(np.r_[lo[:2], hi[:2]]).max() > OFFSET_THRESHOLD_MM:
                # auf 100 m gerundet: bei 1:50 … 1:500 ein ganzes Vielfaches jedes Voxels (0.4/0.8 mm),
                # die Lage im Voxelraster und damit das Ergebnis bleiben gleich wie ohne Versatz
                self._offset = np.array([*np.floor(lo[:2] / OFFSET_GRID_MM) * OFFSET_GRID_MM, 0.0])
                raw = {guid: Geometry(g.verts - self._offset, g.faces) for guid, g in raw.items()}
        return raw

    @property
    def offset_mm(self) -> np.ndarray:
        """Vom Weltsystem abgezogener Versatz (reale mm, nur x/y; 0 bei lokalen Modellen)."""
        self._raw
        return self._offset.copy()

    @cached_property
    def geometry(self) -> dict[str, Geometry]:
        """Triangulierte Geometrie aller Bauteile (IfcElement ohne Aussparungen), je GUID (einmalig berechnet)."""
        return {guid: geo for guid, geo in self._raw.items() if is_element(self.model.by_guid(guid))}

    def class_family_of(self, guid: str) -> str:
        return class_family(self.model.by_guid(guid).is_a(), self.schema_id)

    def extent_mm(self) -> tuple[np.ndarray, np.ndarray]:
        """(min, max) aller Bauteilpunkte in realen mm."""
        lo = np.min([g.verts.min(axis=0) for g in self.geometry.values()], axis=0)
        hi = np.max([g.verts.max(axis=0) for g in self.geometry.values()], axis=0)
        return lo, hi

    def _triangulate(self, only: list | None = None) -> dict[str, Geometry]:
        """Trianguliert alle (oder nur die angegebenen) Elemente und merkt sich die defekten Netze."""
        result, defective = triangulate(self.model, only)
        self.defective |= defective
        return result

    def _triangulate_shifted(self, only: list) -> dict[str, Geometry]:
        """Wie ``_triangulate``, aber um denselben Versatz verschoben wie ``_raw`` (für nachträglich geholte Öffnungen)."""
        return {guid: Geometry(g.verts - self.offset_mm, g.faces) for guid, g in self._triangulate(only).items()}

    # --- Ableitungen aus der Geometrie ------------------------------------

    @cached_property
    def plates(self) -> dict[str, Plate]:
        """Plattenartige Bauteile (Wände, Decken, …) mit Dickenrichtung, je GUID (reale mm, Welt)."""
        result = {}
        for guid, geo in self.geometry.items():
            f = self.class_family_of(guid)
            if f in PLATE_CLASSES and (p := plate(geo.verts, f == "IfcWall")):
                result[guid] = p
        return result

    @cached_property
    def slope(self) -> set[str]:
        """GUIDs der Decken, Dächer und Beläge mit Entwässerungsgefälle (Oberseite flach geneigt)."""
        return {guid for guid, geo in self.geometry.items()
                if self.class_family_of(guid) in ("IfcSlab", "IfcRoof", "IfcCovering")
                and has_slope(geo.mesh(1), SLOPE_DEG)}

    @cached_property
    def filler(self) -> list[Filler]:
        """Fenster, Türen und Vorhangfassaden mit Öffnungskörper und Wirt-Bauteil (falls im IFC)."""
        return find_fillers(self.model, self._raw, self.geometry, self._triangulate_shifted)

    @cached_property
    def voids(self) -> dict[str, list[Geometry]]:
        """Öffnungen ohne Fenster oder Tür (Treppenaugen, Schächte, Durchgänge) je Wirt-GUID (reale mm, Welt)."""
        return find_voids(self.model, self._raw, self.filler)

    @cached_property
    def building_elements(self) -> pd.DataFrame:
        """Eine Zeile je physischem Bauteil mit Darstellung (einmalig berechnet, nicht verändern).

        Die Spalten beschreibt ``element_table`` in core/ifc/table.py.
        """
        return element_table(self.model, self.geometry, self.defective, self.schema_id)
