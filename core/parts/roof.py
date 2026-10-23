"""Dachteile erkennen: Welche Bauteile bilden die Dachschale, welche Träger werden mit dem Dach gedruckt?

Zweck:   Dachbauteile (und Stäbe der Dachkonstruktion im Dachraum) bekommen den Namen «Dach <Geschoss>». Die Aufteilung
         (core/parts/partitioning.py) schneidet sie dadurch als eigenes Dachteil statt als Teil des Geschosses.
Eingabe: IFC-Modell, Zeile der Bauteiltabelle (df.itertuples()), Welt-Z je Geschoss in realen mm.
Ausgabe: Name des Dachteils oder None; Dachzonen als umschliessende Boxen (Welt, reale mm).
"""

import numpy as np

from config import ROOF_ABOVE_ELEVATION_MM, ROOF_INCLINATION_DEG, ROOF_ZONE_MIN_HEIGHT_MM
from core.ifc.assignment import class_family
from core.ifc.model import IfcModel

FRAME_FAMILIES = ("IfcBeam", "IfcMember")      # Stabbauteile: Pfetten, Sparren, Streben, Träger


def roof_part(ifc: IfcModel, z: tuple, elevations: dict[str, float]) -> str | None:
    """Name des Dachteils («Dach <Geschoss>»), wenn das Bauteil zur Dachschale gehört, sonst None.

    Dachschale = Dachbauteil (IfcRoof samt seinen Teilen, IfcSlab.ROOF, IfcCovering.ROOFING; Unterklassen
    wie IfcSlabStandardCase eingeschlossen), das geneigt ist
    (> 5°, auch senkrechte Dachteile) oder als flaches Dach mehr als 1.5 m über der Kote seines
    Geschosses liegt. Flache Dachbauteile auf Bodenhöhe (in ArchiCAD z.B. Bodenaufbauten,
    Vordächer, Terrassen) gehören zum Geschoss.
    """
    if not (_in_roof(ifc, z) or (z.class_family, z.predefined_type) in (("IfcSlab", "ROOF"), ("IfcCovering", "ROOFING"))):
        return None
    if (p := ifc.plates.get(z.guid)) is None:
        return None
    if abs(p.normal_vector[2]) < np.cos(np.radians(ROOF_INCLINATION_DEG)):
        return f"Dach {z.storey}"
    bottom = ifc.geometry[z.guid].verts[:, 2].min()
    return f"Dach {z.storey}" if z.storey in elevations and bottom > elevations[z.storey] + ROOF_ABOVE_ELEVATION_MM else None


def _in_roof(ifc: IfcModel, z: tuple) -> bool:
    """Ein IfcRoof oder Teil eines IfcRoof (Unterklassen eingeschlossen)."""
    return z.class_family == "IfcRoof" or class_family(getattr(z, "aggregate", ""), ifc.schema_id) == "IfcRoof"


def roof_zones(ifc: IfcModel, rows: list, elevations: dict[str, float]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Umschliessende Box (Welt, reale mm) je Dachteil, dessen Dachschale höher als ROOF_ZONE_MIN_HEIGHT_MM ist.

    Niedrige Dachteile (Terrassen, Vordächer) bilden keine Zone: dort liegen nur Stürze in Wänden.
    """
    verts = {}
    for z in rows:
        if name := roof_part(ifc, z, elevations):
            verts.setdefault(name, []).append(ifc.geometry[z.guid].verts)
    zones = {}
    for name, item_list in verts.items():
        points = np.concatenate(item_list)
        lo, hi = points.min(axis=0), points.max(axis=0)
        if hi[2] - lo[2] > ROOF_ZONE_MIN_HEIGHT_MM:
            zones[name] = (lo, hi)
    return zones


def roof_beam(ifc: IfcModel, z: tuple, zones: dict[str, tuple[np.ndarray, np.ndarray]]) -> str | None:
    """Dachteil, zu dem ein Stab der Dachkonstruktion zählt, der in der Dachzone liegt (auch wenn er einem Geschoss
    darunter gehört).

    Stab = Träger oder Stab (``FRAME_FAMILIES``) oder ein Dachbauteil, das keine Platte ist: ArchiCAD exportiert
    Sparren und Pfetten des Dachwerkzeugs als IfcRoof in Balkenform. Solche Stäbe hängen frei in der Luft (unter
    ihnen ist nichts zu drucken) und werden deshalb mit dem Dach gedruckt: Grundriss-Mitte innerhalb der Dachbox,
    Höhe überlappt sie.
    """
    frame = z.class_family in FRAME_FAMILIES or (_in_roof(ifc, z) and z.guid not in ifc.plates)
    if not frame or (g := ifc.geometry.get(z.guid)) is None:
        return None
    lo_t, hi_t = g.verts.min(axis=0), g.verts.max(axis=0)
    center = (lo_t + hi_t) / 2
    for name, (lo, hi) in zones.items():
        if (lo[:2] <= center[:2]).all() and (center[:2] <= hi[:2]).all() and lo_t[2] < hi[2] and hi_t[2] > lo[2]:
            return name
    return None


def roof_name(ifc: IfcModel, z: tuple, elevations: dict[str, float], zones: dict) -> str | None:
    """Dachteil eines Bauteils: Dachschale (``roof_part``) oder Stab in der Dachzone (``roof_beam``), sonst None."""
    return roof_part(ifc, z, elevations) or roof_beam(ifc, z, zones)
