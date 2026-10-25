"""Vorschau-Geometrie (GLB) für den 3D-Viewer.

Eingabe: Netze mit Farbe (glb) bzw. Teile der Erzeugung (stl_preview)
Ausgabe: GLB-Bytes je Geschoss, reduzierte STL-Vorschau je Teil

UI-neutral: Hier entstehen nur Bytes (binäres glTF). Pro Geschoss eine Datei,
damit der Viewer die Geschosse einzeln verschieben kann («auseinander»). Die
Farben werden als Material eingebacken – der Viewer muss nichts einfärben.
"""

import trimesh
from trimesh.visual.material import PBRMaterial

from core.voxels.meshing import decimated

# RGBA je Darstellung (sRGB)
COLORS = {
    "druckbar": (147, 216, 196, 255),          # Statusfarben «Pastell · Mint & Pfirsich» (wie ui/theme.css)
    "kritisch": (255, 201, 163, 255),
    "nicht_druckbar": (244, 166, 180, 255),
    "ausgeschlossen": (214, 217, 222, 46),
    "selection": (66, 133, 255, 255),
    "stl": (255, 107, 44, 255),
    "defekt": (255, 93, 93, 230),
    "ueberhang": (214, 26, 60, 255),
}
# Geschossfarben im IFC-Modus: kühle Töne, die nicht mit den Statusfarben kollidieren
STOREY_COLORS = ["#5AA9FF", "#8E7CFF", "#2CC6C6", "#C07CE8", "#4F7CFF", "#7BD0A0", "#9AA8FF", "#3FA7D6"]
IFC_OPACITY = 0.18


def storey_color(rank: int) -> str:
    return STOREY_COLORS[rank % len(STOREY_COLORS)]


def _rgba(color: str) -> tuple:
    """Farbschlüssel aus COLORS oder Hexfarbe «#rrggbb» (transparent wie im IFC-Modus)."""
    if color in COLORS:
        return COLORS[color]
    h = color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), round(IFC_OPACITY * 255))


def _linear(rgba) -> list[float]:
    """sRGB (0–255) → lineare Farbwerte 0–1, wie glTF sie für baseColorFactor erwartet.

    Ohne Umrechnung interpretiert three.js die sRGB-Werte als linear und zeigt sie
    deutlich heller und blasser an.
    """
    color = [(c / 255 / 12.92) if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in rgba[:3]]
    return color + [rgba[3] / 255]


def glb(meshes: list[tuple[trimesh.Trimesh, str]], sharp: bool = True) -> bytes:
    """Ein GLB aus (Mesh, Farbe)-Paaren; gleichfarbige Netze werden zusammengefasst.

    Farbe: Schlüssel aus COLORS oder Hexfarbe «#rrggbb» (Geschossfarbe, transparent).

    ``sharp``: Kanten hart schattieren (Bauteile). Für die geglättete Hülle aus, das spart ⅔ der Datenmenge.
    """
    scene_obj = trimesh.Scene()
    for color in dict.fromkeys(f for _, f in meshes):
        parts = [m for m, f in meshes if f == color]
        mesh = trimesh.util.concatenate(parts)
        if sharp:
            mesh.unmerge_vertices()                   # je Fläche eigene Normalen
        rgba = _rgba(color)
        mesh.visual = trimesh.visual.TextureVisuals(material=PBRMaterial(
            baseColorFactor=_linear(rgba), metallicFactor=0.05, roughnessFactor=0.6, doubleSided=True,
            alphaMode="BLEND" if rgba[3] < 255 else "OPAQUE"))
        scene_obj.add_geometry(mesh, geom_name=color)
    return scene_obj.export(file_type="glb", include_normals=True)


def stl_preview(parts: dict[str, trimesh.Trimesh], max_faces: int,
                marks: dict[str, trimesh.Trimesh] | None = None) -> dict[str, bytes]:
    """GLB je Geschoss-Teil, gemeinsam auf ``max_faces`` Dreiecke reduziert (Browser-Budget).

    ``marks``: rote Markierung der Stellen, die Stützen brauchen (core/parts/overhangs.py), im selben GLB wie
    das Teil – so folgt sie dem Ausblenden und «auseinander» im Viewer.
    """
    marks = marks or {}
    combined = sum(len(m.faces) for m in parts.values()) or 1
    fraction = min(1.0, max(0.0, max_faces - sum(len(m.faces) for m in marks.values())) / combined)
    return {name: glb([(decimated(m, fraction), "stl")] + ([(marks[name], "ueberhang")] if name in marks else []),
                      sharp=False)
            for name, m in parts.items()}

