"""Verbinder einer Fuge planen: wo stehen die drei Zapfen, wie gross und in welcher Form?

Je Fuge (Teil a unten, Teil b oben) in drei Schritten (``JointPlanner``):
  1. Flächen bestimmen: Kontaktfläche (Wandkronen und Stützenköpfe, auf denen das obere Teil aufliegt),
     mögliche Zapfenhöhe je Spalte und der Bereich, in dem die Tasche in der Decke Platz hat.
  2. Kandidaten sammeln: Mittellinie der Kontaktflächen (lokales Maximum des Randabstands).
  3. Drei Punkte wählen, möglichst weit auseinander (grösstes Dreieck): Das obere Teil liegt statisch
     bestimmt auf. An jedem Punkt passt der grösste Zapfen, der auf die Krone passt und dessen Tasche
     in der Decke liegt – länglich (Wand) als Rechteck längs der Wand, gedrungen (Stütze, Ecke) rund.

Eingabe: Voxelgitter, Label-Gitter, Teile a und b, Schicht kc der Kontaktfläche, Passungsspiel [mm]
Ausgabe: Liste von ``Connector`` (leer, wo nichts passt)
"""

from typing import NamedTuple

import numpy as np
from scipy.ndimage import distance_transform_edt, maximum_filter

from config import (CONNECTOR_MIN_SPACING_MM, CONTACT_SHAPE_RADIUS_MM, ELONGATION_RATIO, MIN_ENGAGEMENT_MM,
                    PEG_DEPTH_RATIO, PEG_MAX_ENGAGEMENT_MM, PEG_RECT_WIDTH_MM, PEG_ROUND_DIAMETER_MM)
from core.connectors.geometry import Connector, rectangle_points
from core.voxels.grid import VoxelGrid

_ATTEMPTS = 300       # Kandidaten je Punkt, bis einer passt


class _Candidates(NamedTuple):
    """Mögliche Zapfenmitten einer Fuge: Gitterzellen (i, j) und ihre Lage in mm relativ zum Gitterursprung."""
    i: np.ndarray
    j: np.ndarray
    xy: np.ndarray


def _run_length_up(labels: np.ndarray, value: int, k0: int, cap: int) -> np.ndarray:
    """Je Spalte: Anzahl aufeinanderfolgender Schichten ab k0 aufwärts mit Label ``value`` (höchstens ``cap``)."""
    run = np.zeros(labels.shape[:2], dtype=np.int32)
    held = np.ones(run.shape, dtype=bool)
    for k in range(k0, min(labels.shape[2], k0 + cap)):
        held &= labels[:, :, k] == value
        if not held.any():
            break
        run += held
    return run


class JointPlanner:
    """Plant die Verbinder einer Fuge zwischen Teil a (unten, oberste Schicht kc) und Teil b (ab Schicht kc+1)."""

    def __init__(self, voxel_grid: VoxelGrid, labels: np.ndarray, a: int, b: int, kc: int, clearance: float):
        self.a, self.b, self.clearance = a, b, clearance
        self.pitch = voxel_grid.pitch
        self.ox, self.oy = voxel_grid.origin[:2]
        kf = kc + 1
        self.z_joint = float(voxel_grid.origin[2] + (kf - 0.5) * self.pitch)
        contact = (labels[:, :, kc] == a) & (labels[:, :, kf] == b)
        thickness = _run_length_up(labels, b, kf, int(np.ceil(PEG_MAX_ENGAGEMENT_MM / PEG_DEPTH_RATIO / self.pitch)) + 1)
        slab_n = int(np.bincount(thickness[labels[:, :, kf] == b]).argmax())     # typische Deckendicke (über Wänden
        self.height_mm = np.minimum(PEG_DEPTH_RATIO * np.minimum(thickness, slab_n) * self.pitch,  # geht das Teil weiter)
                                    PEG_MAX_ENGAGEMENT_MM)
        self.contact = contact & (self.height_mm >= MIN_ENGAGEMENT_MM)
        self.slab = thickness * self.pitch >= MIN_ENGAGEMENT_MM + clearance                 # hier darf die Tasche liegen

    def plan(self) -> list[Connector]:
        """Bis zu drei Verbinder: 1 am weitesten vom Schwerpunkt, 2 am weitesten von 1, 3 grösstes Dreieck mit 1 und 2."""
        if not self.contact.any():
            return []
        candidates = self._candidates()
        if not len(candidates.i):
            return []
        xy, result = candidates.xy, []
        first = self._best(candidates, np.hypot(*(xy - xy.mean(axis=0)).T), result)
        if first is None:
            return result
        result.append(first)
        p1 = np.array([first.x - self.ox, first.y - self.oy])
        second = self._best(candidates, np.hypot(*(xy - p1).T), result)
        if second is None:
            return result
        result.append(second)
        p2 = np.array([second.x - self.ox, second.y - self.oy])
        area = np.abs((p2[0] - p1[0]) * (xy[:, 1] - p1[1]) - (p2[1] - p1[1]) * (xy[:, 0] - p1[0]))
        third = self._best(candidates, area, result)
        if third is not None:
            result.append(third)
        return result

    def _candidates(self) -> _Candidates:
        """Mittellinie der Kontaktflächen (lokales Maximum des Randabstands), breit genug für den kleinsten Zapfen."""
        distance = distance_transform_edt(np.pad(self.contact, 1))[1:-1, 1:-1]
        center = self.contact & (distance >= maximum_filter(distance, size=3))
        ii, jj = np.nonzero(center & (distance * self.pitch >= min(min(PEG_ROUND_DIAMETER_MM), min(PEG_RECT_WIDTH_MM)) / 2))
        return _Candidates(ii, jj, np.column_stack([ii, jj]).astype(float) * self.pitch)

    def _best(self, candidates: _Candidates, value: np.ndarray, chosen: list[Connector]) -> Connector | None:
        """Bester Kandidat nach ``value``; zuerst nur kräftige Zapfen (Rechteck oder rund ≥ Rechteckbreite × 2),
        so landen die Punkte auf geraden Wandstücken und Stützen statt in schmalen Ecken."""
        xy = candidates.xy
        free = np.ones(len(xy), dtype=bool)
        for v in chosen:
            free &= np.hypot(xy[:, 0] - (v.x - self.ox), xy[:, 1] - (v.y - self.oy)) >= CONNECTOR_MIN_SPACING_MM
        order = np.argsort(-value, kind="stable")
        order = order[free[order]][:_ATTEMPTS]
        fallback_plan = None
        for n in order:
            v = self._form(int(candidates.i[n]), int(candidates.j[n]))
            if v is not None and (not v.is_round or v.width >= 2 * min(PEG_RECT_WIDTH_MM)):
                return v
            fallback_plan = fallback_plan or v
        return fallback_plan

    def _form(self, i: int, j: int) -> Connector | None:
        """Grösster Zapfen, der an (i, j) auf die Krone passt (Fuss) und dessen Tasche in der Decke liegt."""
        x, y = self.ox + i * self.pitch, self.oy + j * self.pitch
        clearance = self.clearance
        margin = self.pitch / 2                                  # Zellmitten: halbe Zelle Spielraum zum Rand
        angle, ratio = self._direction(i, j)
        if ratio >= ELONGATION_RATIO:
            sizes = [(2 * bb, bb, False) for bb in PEG_RECT_WIDTH_MM]
        else:
            sizes = [(d, d, True) for d in PEG_ROUND_DIAMETER_MM]
        for length, width, is_round in sizes:
            footprint = rectangle_points(x, y, max(length - 2 * margin, 0), max(width - 2 * margin, 0), angle)
            socket = rectangle_points(x, y, length + 2 * clearance, width + 2 * clearance, angle)
            if is_round:     # Kreis im Quadrat: nur die Punkte im Kreis prüfen
                footprint = footprint[np.hypot(footprint[:, 0] - x, footprint[:, 1] - y) <= (length / 2 - margin) + 1e-9]
                socket = socket[np.hypot(socket[:, 0] - x, socket[:, 1] - y) <= length / 2 + clearance + 1e-9]
            if self._lies_in(self.contact, footprint) and self._lies_in(self.slab, socket):
                return Connector(self.a, self.b, x, y, self.z_joint, width, length,
                                 float(self.height_mm[i, j]), angle, is_round)
        return None

    def _direction(self, i: int, j: int) -> tuple[float, float]:
        """Lokale Längsrichtung und Längsverhältnis der Kontaktfläche um (i, j)."""
        r = int(np.ceil(CONTACT_SHAPE_RADIUS_MM / self.pitch))
        fi, fj = np.nonzero(self.contact[max(0, i - r):i + r + 1, max(0, j - r):j + r + 1])
        if len(fi) < 3:                                  # zu wenig Zellen für eine Richtung
            return 0.0, 1.0
        values, vectors = np.linalg.eigh(np.cov(np.vstack([fi, fj]).astype(float)))
        long = vectors[:, 1]
        return float(np.arctan2(long[1], long[0])), float(np.sqrt(values[1] / max(values[0], 1e-9)))

    def _lies_in(self, mask: np.ndarray, points: np.ndarray) -> bool:
        """True, wenn alle Punkte (mm) in Zellen der Maske liegen."""
        i = np.rint((points[:, 0] - self.ox) / self.pitch).astype(int)
        j = np.rint((points[:, 1] - self.oy) / self.pitch).astype(int)
        if (i < 0).any() or (j < 0).any() or (i >= mask.shape[0]).any() or (j >= mask.shape[1]).any():
            return False
        return bool(mask[i, j].all())
