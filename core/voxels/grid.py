"""Voxelgitter und Bauteil: die beiden Datenbehälter der Hülle.

``VoxelGrid`` ist das gemeinsame Gitter aller Bauteile (Bool-Matrix samt Ursprung, Pitch, Grundrissen
und Dach-Labels). Es kann Körper einsetzen oder ausleeren (``place``) und sich vernetzen lassen
(``grid_to_mesh``). ``BuildingElement`` beschreibt ein zu druckendes Bauteil, bevor es voxelisiert wird.

Eingabe: Bauteil-Netze bzw. Körper im Modellmass [mm]
Ausgabe: Voxelgitter bzw. wasserdichtes Mesh
"""

from dataclasses import dataclass, field

import numpy as np
import trimesh

from core.voxels.mesh_voxels import frame, inside_voxel, surface_voxel
from core.voxels.meshing import marching_cubes, postprocessed


@dataclass
class VoxelGrid:
    """Bool-Matrix; Voxel [i, j, k] hat das Zentrum origin + (i, j, k) · pitch (Modell-mm).

    Für die Aufteilung (core/parts/partitioning.py): ``floor_plans`` je Geschoss (2D-Maske der Spalten
    seiner Bauteile, Räume eingeschlossen) und ``roof`` (Index in ``roof_names`` je Voxel, −1 = kein Dach).
    """
    matrix: np.ndarray
    origin: np.ndarray
    pitch: float
    floor_plans: dict[str, np.ndarray] = field(default_factory=dict, repr=False)
    roof: np.ndarray | None = field(default=None, repr=False)
    roof_names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)         # übersprungene Bauteile (mit GUID)

    def grid_to_mesh(self, k_from: int = 0, k_to: int | None = None, *, postprocess: bool = True) -> trimesh.Trimesh:
        """Vernetzt die Z-Schichten [k_from, k_to) zu einem wasserdichten Mesh."""
        part = self.matrix[:, :, k_from:k_to]
        origin = self.origin + np.array([0.0, 0.0, k_from * self.pitch])
        mesh = marching_cubes(part, origin, self.pitch)
        return postprocessed(mesh) if postprocess else mesh

    def _mask(self, body: trimesh.Trimesh) -> tuple[tuple[slice, ...], np.ndarray] | None:
        """(Gitterausschnitt, Maske) der Voxel, deren Mitte im geschlossenen Körper liegt; None ausserhalb."""
        triangles = body.triangles / self.pitch
        lo, size = frame(triangles)
        mask = inside_voxel(triangles, lo, size)
        if mask is None:
            mask = surface_voxel(triangles, lo, size)
        a = lo - np.rint(self.origin / self.pitch).astype(np.int64)   # lokale → Gitter-Indizes
        start_idx, stop_idx = np.maximum(a, 0), np.minimum(a + size, self.matrix.shape)
        if np.any(stop_idx <= start_idx):
            return None
        target = tuple(slice(v, b) for v, b in zip(start_idx, stop_idx))
        return target, mask[tuple(slice(v - x, b - x) for v, b, x in zip(start_idx, stop_idx, a))]

    def place(self, body: trimesh.Trimesh, value: bool) -> int:
        """Füllt (True) oder leert (False) alle Voxel, deren Mitte im geschlossenen Körper liegt.

        Teile ausserhalb des Gitters werden ignoriert. Rückgabe: Anzahl geänderter Voxel.
        """
        if (hits := self._mask(body)) is None:
            return 0
        target, mask = hits
        previous = self.matrix[target].copy()
        if value:
            self.matrix[target] |= mask
        else:
            self.matrix[target] &= ~mask
        return int((previous != self.matrix[target]).sum())

    def count_inside(self, body: trimesh.Trimesh) -> int:
        """Anzahl belegter Voxel im Körper."""
        if (hits := self._mask(body)) is None:
            return 0
        target, mask = hits
        return int((self.matrix[target] & mask).sum())


@dataclass
class BuildingElement:
    """Ein zu druckendes Bauteil im Modellmass [mm]."""
    mesh: trimesh.Trimesh
    thickening: int = 0                       # Voxel je Seite (nur Bauteile ausserhalb von Paketen)
    storey: str = ""                        # IFC-Geschoss (Grundriss für die Fugen)
    roof: str | None = None                   # Name des Dachteils, falls Dachbauteil
    flatten: bool = False                       # Gefälle ausgleichen (Spalten tiefste bis höchste Schicht füllen)
    guid: str = ""                            # für Warnungen, falls das Bauteil nicht voxelisierbar ist
    voids: list[trimesh.Trimesh] = field(default_factory=list)   # Öffnungen ohne Füller (nur aus diesem Bauteil)
