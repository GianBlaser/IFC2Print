"""Tests für core/parts/overhangs: Brücke oder Stützen, Bett oder Modell, rote Markierung."""

import numpy as np
from scipy.ndimage import binary_dilation

from core.parts.overhangs import _with_neighbours, mark, message, overhangs, summary

PITCH = 0.4


def _table(span: int, floor: bool = False) -> np.ndarray:
    """Label-Gitter: zwei Wandscheiben (je 2 Voxel dick) mit einer Platte darüber; ``span`` Voxel lichte Weite.

    ``floor``: zusätzlich eine Bodenplatte, auf der die Wände stehen (dann liegt unter der Platte das Modell).
    """
    labels = np.full((span + 4, 30, 12), -1, dtype=np.int16)
    labels[:2, :, :10] = labels[-2:, :, :10] = 0
    labels[:, :, 10:] = 0
    if floor:
        labels[:, :, 0] = 0
    return labels


def test_short_span_is_a_bridge():
    o = overhangs(_table(span=8), {0: "EG"}, PITCH, np.zeros(3))[0]       # 3.2 mm lichte Weite
    assert o.support_mm2 == 0 and o.bridge_mm2 > 0
    assert summary([o]).startswith("Überhänge: alle Teile ohne Stützen druckbar")


def test_long_span_needs_supports_from_the_bed():
    o = overhangs(_table(span=60), {0: "EG"}, PITCH, np.zeros(3))[0]      # 24 mm: Mitte weiter als 5 mm vom Auflager
    assert o.relevant and o.on_model_mm2 == 0
    width = 60 - 2 * 12                                                    # Rand bis BRIDGE_MAX_MM / 2 trägt als Brücke
    assert abs(o.support_mm2 - width * 30 * PITCH ** 2) <= 2 * 30 * PITCH ** 2
    assert o.largest[2] == 10 * PITCH                                      # Höhe über dem Bett
    assert "Druckbett" in message(o, None)
    assert summary([o]) is None


def test_supports_over_the_model_suggest_reassignment():
    o = overhangs(_table(span=60, floor=True), {0: "EG"}, PITCH, np.zeros(3))[0]
    assert o.relevant and o.on_model_mm2 == o.support_mm2
    assert "zuordnen" in message(o, "IfcSlab «Decke»")


def test_part_rests_on_its_own_lowest_layer():
    labels = np.full((70, 30, 30), -1, dtype=np.int16)
    labels[:, :, 20:22] = 3                                                # schwebt im Gitter, liegt aber als Teil auf dem Bett
    o = overhangs(labels, {3: "Dach"}, PITCH, np.zeros(3))[0]
    assert o.support_mm2 == 0 and o.bridge_mm2 == 0


def test_mark_merges_a_rectangle_into_one_box():
    o = overhangs(_table(span=60), {0: "EG"}, PITCH, np.zeros(3))[0]
    m = mark(o, PITCH, np.zeros(3))
    assert len(m.faces) == 12                                              # ein Quader für die ganze Fläche
    lo, hi = m.bounds
    assert lo[2] < 10 * PITCH - PITCH / 2 < hi[2]                          # ragt unter die Plattenunterseite


def test_neighbours_match_binary_dilation():
    rng = np.random.default_rng(1)
    layer = rng.random((40, 30)) > 0.9
    assert (_with_neighbours(layer) == binary_dilation(layer, structure=np.ones((3, 3), dtype=bool))).all()
