"""Bauteilpakete: mehrschichtige und direkt anliegende Platten gemeinsam skalieren.

Zwei Probleme echter Architekturmodelle löst dieses Modul an der Wurzel:

* Eine Aussenwand kommt oft als mehrere IfcWall-Schichten (Beton, Dämmung,
  Bekleidung). Einzeln betrachtet ist die Bekleidung «zu dünn» und würde aufgedickt –
  die Wand wird dadurch zu dick, obwohl das Paket längst druckbar ist.
* Eine Wand zwischen 1 und 2 Voxeln Dicke trifft je nach Lage im Gitter 1 oder 2
  Voxelmitten. Gleiche Wandtypen werden dadurch unterschiedlich dick.

Ablauf:
  1. Plattenartige Bauteile (Wände, Decken, Dächer, Bekleidungen) erhalten über ihre
     orientierte Box eine Dickenrichtung (Normale, kleinste Kante) – core/packages/plates.py.
  2. Parallele Platten, die sich berühren (Spalt ≤ Toleranz) und in der Fläche
     überlappen, bilden ein Paket (Union-Find, ``group_plates``). Entscheidend ist die Paketdicke
     – core/packages/thickness.py.
  3. Jedes Paket wird nur entlang seiner Normale affin skaliert: auf ganze Voxel
     gerundet, mindestens die Mindestdicke. Länge und Höhe bleiben. Bei achsparalleler
     Normale liegen die Flächen danach knapp innerhalb von Voxelgrenzen – gleiche
     Wandtypen werden überall exakt gleich viele Voxel dick – core/packages/scaling.py.

Eingabe: Platten (``Plate``) aller Bauteile, Toleranz [mm]
Ausgabe: Paketnummer je Platte (``group_plates``); die übrigen Namen stehen von hier aus weiter zur Verfügung
"""

import numpy as np

from config import PACKAGE_PARALLEL_DEG
from core.packages.plates import Plate


_PARALLEL_COS = np.cos(np.radians(PACKAGE_PARALLEL_DEG))     # Normalen gelten als parallel


def _touch(a: Plate, b: Plate, tolerance: float) -> bool:
    """Parallel vorausgesetzt: Spalt entlang der Normale ≤ toleranz und Überlappung in der Fläche."""
    alo, ahi = a.span(a.normal_vector)
    blo, bhi = b.span(a.normal_vector)
    if max(blo - ahi, alo - bhi) > tolerance:
        return False
    for direction in a.axes[1:]:
        alo, ahi = a.span(direction)
        blo, bhi = b.span(direction)
        if min(ahi, bhi) - max(alo, blo) <= tolerance:
            return False
    return True


def group_plates(plates: list[Plate], tolerance: float) -> list[int]:
    """Paketnummer (0, 1, …) je Platte; berührende parallele Platten teilen eine Nummer."""
    n = len(plates)
    uf_parent = list(range(n))

    def root_node(i: int) -> int:
        while uf_parent[i] != i:
            uf_parent[i] = uf_parent[uf_parent[i]]
            i = uf_parent[i]
        return i

    if n:
        lo = np.array([p.points.min(axis=0) for p in plates]) - tolerance
        hi = np.array([p.points.max(axis=0) for p in plates]) + tolerance
        normal_vectors = np.array([p.normal_vector for p in plates])
        for i in range(n - 1):
            near = ((np.abs(normal_vectors[i + 1:] @ normal_vectors[i]) >= _PARALLEL_COS)
                   & (lo[i + 1:] <= hi[i]).all(axis=1) & (hi[i + 1:] >= lo[i]).all(axis=1))
            for j in np.nonzero(near)[0] + i + 1:
                if root_node(i) != root_node(j) and _touch(plates[i], plates[j], tolerance):
                    uf_parent[root_node(j)] = root_node(i)
    seq_number: dict[int, int] = {}
    return [seq_number.setdefault(root_node(i), len(seq_number)) for i in range(n)]
