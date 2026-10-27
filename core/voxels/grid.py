"""Voxelgitter und Bauteil: die beiden Datenbehälter der Hülle.

``VoxelGrid`` ist das gemeinsame Gitter aller Bauteile (Bool-Matrix samt Ursprung, Pitch, Grundrissen
und Dach-Labels). Es kann Körper einsetzen oder ausleeren (``place``) und sich vernetzen lassen
(``grid_to_mesh``). ``BuildingElement`` beschreibt ein zu druckendes Bauteil, bevor es voxelisiert wird.

Eingabe: Bauteil-Netze bzw. Körper im Modellmass [mm]
Ausgabe: Voxelgitter bzw. wasserdichtes Mesh
"""

from collections.abc import Callable
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
    # Feldwerte feiner als ein Voxel (flache Laibungen): je Aufruf von place_level (Gitterindizes N×3, Werte N)
    levels: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list, repr=False)

    def grid_to_mesh(self, k_from: int = 0, k_to: int | None = None, *, postprocess: bool = True) -> trimesh.Trimesh:
        """Vernetzt die Z-Schichten [k_from, k_to) zu einem wasserdichten Mesh."""
        part = self.scalar_field(self.matrix[:, :, k_from:k_to], np.array([0, 0, k_from]))
        origin = self.origin + np.array([0.0, 0.0, k_from * self.pitch])
        mesh = marching_cubes(part, origin, self.pitch)
        return postprocessed(mesh) if postprocess else mesh

    def scalar_field(self, mask: np.ndarray, lo: np.ndarray) -> np.ndarray:
        """``mask`` (Ausschnitt ab Gitterindex ``lo``) als Feld für Marching Cubes (Fläche bei 0.5).

        Gespeicherte Feldwerte (``place_level``) gelten nur, wo sie noch zum Voxel passen (≥ 0.5 ↔ voll);
        wurde der Voxel danach gefüllt oder geleert, gilt wieder die Bool-Matrix.
        """
        result = mask.astype(np.float32)
        if not self.levels:
            return result
        index = np.concatenate([i for i, _ in self.levels]) - lo
        values = np.concatenate([v for _, v in self.levels])
        inside = np.all((index >= 0) & (index < mask.shape), axis=1)
        index, values = index[inside], values[inside]
        fits = mask[tuple(index.T)] == (values >= 0.5)
        result[tuple(index[fits].T)] = values[fits]
        return result

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

    def place_level(self, body: trimesh.Trimesh, level: Callable[[np.ndarray], np.ndarray]) -> int:
        """Setzt die Voxel im Körper nach einem Feld: ``level(Mitten [mm])`` ≥ 0.5 = voll.

        Das Feld (linear über den Abstand zur gewünschten Fläche, 1 je Pitch) bleibt für die Vernetzung
        gespeichert: Marching Cubes legt die Fläche dann auch zwischen zwei Voxelmitten. Rückgabe: Anzahl
        Voxel, die sich in der Bool-Matrix oder nur im Feld (Wert zwischen 0 und 1) ändern.
        """
        if (hits := self._mask(body)) is None:
            return 0
        target, mask = hits
        index = np.argwhere(mask) + np.array([s.start for s in target])
        values = np.clip(level(self.origin + index * self.pitch), -1.0, 2.0).astype(np.float32)
        values[np.isclose(values, 0.5)] += 1e-3       # genau 0.5: Fläche durch die Voxelmitte, entartete Dreiecke
        cells = tuple(index.T)
        previous = self.matrix[cells]
        self.matrix[cells] = values >= 0.5
        self.levels.append((index, values))
        return int(((previous != self.matrix[cells]) | ((values > 0) & (values < 1))).sum())

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
