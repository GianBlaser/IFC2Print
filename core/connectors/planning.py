"""Steckverbinder zwischen den Geschossteilen.

Planung (``plan_connectors``) auf dem Label-Gitter, Geometrie (``apply_connectors``) als echte
Kegelstümpfe per Boolean auf den fertigen Netzen. Die Masse stehen in config.py (Abschnitt Steckverbinder).

Prinzip je Fuge (Teil n unten, Teil n+1 oben, beide stehen mit ihrer Unterseite auf dem Bett):
  * Die Unterseite von Teil n+1 ist eine Decke; Teil n trägt sie mit Wänden und Stützen. Nur diese
    Kontaktflächen (Wandkronen, Stützenköpfe) bekommen Verbinder – keine Säulen im Raum.
  * Drei Punkte je Fuge, möglichst weit auseinander (grösstes Dreieck): Das obere Teil liegt statisch
    bestimmt auf.
  * Form nach der Kontaktfläche: länglich (Wand) → rechteckiger Zapfen längs der Wand, gedrungen
    (Stütze, Ecke) → runder Zapfen. Der Zapfen wächst aus der Krone nach oben und verjüngt sich
    (Kegelstumpf); die Tasche in der Deckenunterseite hat ringsum und oben das Passungsspiel des
    Druckerprofils als Luft. Das obere Teil wird nur aufgelegt, es rastet nicht ein.
Wo nichts passt (Krone zu schmal, Decke zu dünn), entsteht kein Verbinder – mit Warnung.

Aufbau: diese Datei findet die Fugen (``plan_connectors``); die Verbinder einer Fuge plant
core/connectors/joint.py, Zapfen und Taschen rechnet core/connectors/geometry.py.

Eingabe: Voxelgitter, Aufteilung (``Partition``), Passungsspiel [mm]
Ausgabe: Liste von ``Connector`` und Warnungen (Fugen mit weniger als dem Soll an Verbindern)
"""

import numpy as np

from config import CONNECTORS_PER_JOINT, CONTACT_MIN_COLUMNS, CONTACT_MIN_PLANE_RATIO
from core.connectors.geometry import Connector
from core.connectors.joint import JointPlanner
from core.parts.partitioning import Partition
from core.voxels.grid import VoxelGrid


_PAIR_CODE = 4096     # Teilpaar (a, b) als eine Zahl a·4096 + b – reicht für bis zu 4096 Teile

def _contacts(labels: np.ndarray) -> dict[tuple[int, int], dict[int, int]]:
    """Je Paar (unten, oben): Anzahl Spalten, in denen beide direkt übereinander liegen, je Schicht k (unten)."""
    tally: dict[tuple[int, int], dict[int, int]] = {}
    for k in range(labels.shape[2] - 1):
        a, b = labels[:, :, k], labels[:, :, k + 1]
        touches = (a >= 0) & (b >= 0) & (a != b)
        if touches.any():
            codes, n = np.unique(a[touches].astype(np.int32) * _PAIR_CODE + b[touches], return_counts=True)
            for code, count in zip(codes, n):
                tally.setdefault((int(code) // _PAIR_CODE, int(code) % _PAIR_CODE), {})[k] = int(count)
    return tally


def plan_connectors(voxel_grid: VoxelGrid, partition: Partition, clearance_mm: float) -> tuple[list[Connector], list[str]]:
    """Positionen und Masse aller Verbinder; Warnungen für Fugen ohne (genug) Verbinder."""
    labels = partition.labels
    plan: list[Connector] = []
    warnings: list[str] = []
    levels = []
    for (a, b), planes in _contacts(labels).items():
        large = max(planes.values())
        levels += [(kc, a, b) for kc, n in planes.items() if n >= max(CONTACT_MIN_COLUMNS, CONTACT_MIN_PLANE_RATIO * large)]
    for kc, a, b in sorted(levels):
        found = JointPlanner(voxel_grid, labels, a, b, kc, clearance_mm).plan()
        plan += found
        if len(found) < CONNECTORS_PER_JOINT:
            warnings.append(f"Fuge «{partition.names[a]}» → «{partition.names[b]}»: nur {len(found)} von "
                             f"{CONNECTORS_PER_JOINT} Steckverbindern (Wandkronen zu schmal oder Decke zu dünn).")
    return plan, warnings
