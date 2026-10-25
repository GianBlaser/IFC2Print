"""Isometrische Druckbett-Grafik (ui/bed_iso.py): gültiges SVG, sechs Masszahlen, alle innerhalb der Grafik."""

import re
import xml.etree.ElementTree as ET

import pytest

from ui.bed_iso import H, W, bed_iso_svg


@pytest.mark.parametrize("bed, model", [((250, 210, 220), (124, 69, 94)), ((180, 180, 180), (124, 69, 94)),
                                        ((360, 360, 360), (40, 30, 20))])
@pytest.mark.parametrize("level", ["ok", "knapp", "gross"])
def test_bed_iso_svg(bed, model, level):
    html = bed_iso_svg(bed, model, level)
    root = ET.fromstring(html)                                    # ganzes Stück ist wohlgeformtes XML
    svg = root.find("svg")
    assert svg is not None and (svg.get("width"), svg.get("height")) == (str(W), str(H))
    labels = root.findall("span")
    assert len(labels) == 6
    assert sorted(span.text for span in labels) == sorted(f"{round(v)} mm" for v in (*model, *bed))
    for span in labels:
        style = span.get("style")
        x = float(re.search(r"left:(-?[\d.]+)px", style).group(1))
        y = float(re.search(r"top:(-?[\d.]+)px", style).group(1))
        assert 0 <= x <= W and 0 <= y <= H
