"""Modellbild für den PDF-Report: die Druckteile isometrisch, je Teil in seiner Geschossfarbe (Matplotlib).

Eingabe: Druckteile und Stützstellen-Markierungen der Erzeugung, Farbe je Teil
Ausgabe: PNG-Bytes (1000 × 680 px) oder None ohne Teile (Prüfbericht)
"""

import io

import matplotlib
matplotlib.use("Agg")   # headless, keine GUI nötig
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from matplotlib.colors import to_rgb
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from core.voxels.meshing import decimated

MAX_FACES = 40_000                                 # Dreiecke im Bild (mplot3d sortiert jedes einzeln)
BACKGROUND = "#F6F4F0"
SUPPORT_COLOR = "#D61A3C"                          # Stützstellen, wie im Viewer (preview.COLORS["ueberhang"])
_LIGHT = np.array([-1.0, -1.0, 2.0]) / np.linalg.norm([-1.0, -1.0, 2.0])


def model_png(parts: dict[str, trimesh.Trimesh], marks: dict[str, trimesh.Trimesh],
              colors: dict[str, str]) -> bytes | None:
    """Isometrische Ansicht aller Teile; die Teile werden gemeinsam auf MAX_FACES Dreiecke reduziert."""
    if not parts:
        return None
    mark_faces = sum(len(m.faces) for m in marks.values())
    fraction = min(1.0, max(0.0, MAX_FACES - mark_faces) / (sum(len(m.faces) for m in parts.values()) or 1))
    meshes = [(decimated(m, fraction), colors.get(name, "#FF6B2C")) for name, m in parts.items()]
    meshes += [(m, SUPPORT_COLOR) for m in marks.values()]
    # Ein einziges Polygon-Set: mplot3d sortiert nur innerhalb einer Sammlung nach Tiefe
    triangles = np.concatenate([m.triangles for m, _ in meshes])
    face_colors = np.concatenate([_shaded(m, color) for m, color in meshes])

    fig = plt.figure(figsize=(10, 6.8), dpi=100, facecolor=BACKGROUND)
    ax = fig.add_subplot(projection="3d", facecolor=BACKGROUND)
    ax.add_collection3d(Poly3DCollection(triangles, facecolors=face_colors, edgecolors="none", linewidths=0))
    low, high = triangles.reshape(-1, 3).min(axis=0), triangles.reshape(-1, 3).max(axis=0)
    ax.set(xlim=(low[0], high[0]), ylim=(low[1], high[1]), zlim=(low[2], high[2]))
    ax.set_box_aspect(np.maximum(high - low, 1e-6))
    ax.view_init(elev=30, azim=-60)
    ax.set_axis_off()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", pad_inches=0.1, facecolor=BACKGROUND)
    plt.close(fig)
    return buffer.getvalue()


def _shaded(mesh: trimesh.Trimesh, color: str) -> np.ndarray:
    """RGB je Dreieck: Grundfarbe × (0.55 + 0.45 · max(0, n·l)), Licht von schräg oben."""
    brightness = 0.55 + 0.45 * np.clip(mesh.face_normals @ _LIGHT, 0.0, None)
    return np.clip(np.outer(brightness, to_rgb(color)), 0.0, 1.0)
