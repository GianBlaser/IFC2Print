"""Tests für core/analysis/surroundings: Umgebung über Name, Typname, Layer und Grundstück erkennen."""

import pandas as pd

from core.analysis.surroundings import is_surroundings


def _table(**columns):
    basis = {"name": ["Aussenwand"], "type_name": [""], "layer": [""], "on_site": [False]}
    return pd.DataFrame({**basis, **columns})


def test_name_type_and_layer():
    assert is_surroundings(_table(name=["Stützmauer Ost"])).all()
    assert is_surroundings(_table(type_name=["Gelände-Kante"])).all()
    assert is_surroundings(_table(name=["Aussenwände EG"], layer=["011 Stützwände"])).all()   # 4503
    assert not is_surroundings(_table(layer=["020 Stützen"])).any()                          # Stützen ≠ Stützwand


def test_site_only_when_storeys_used():
    df = pd.DataFrame({"name": ["Wand"] * 4, "type_name": "", "layer": "",
                       "on_site": [True, False, False, False]})
    assert is_surroundings(df).tolist() == [True, False, False, False]
    everything_on_site = df.assign(on_site=True)     # Modell ohne Geschosse
    assert not is_surroundings(everything_on_site).any()


def test_missing_columns():
    assert is_surroundings(pd.DataFrame({"name": ["Stützmauer", "Wand"]})).tolist() == [True, False]


# --- Wortgrenzen, Klassen, Lage, Ausreisser (Analysebericht B-06, B-07) ------------

def test_railing_is_not_surroundings():
    """«gelände» steckt in «Geländer» – früher wurden die NEST-Geländer zur Umgebung."""
    assert not is_surroundings(_table(name=["Geländer Balkon"])).any()
    assert not is_surroundings(_table(type_name=["Gelaender Stahl"])).any()
    assert is_surroundings(_table(name=["Geländekante Nord"])).all()
    assert is_surroundings(_table(name=["Retaining Wall"])).all()


def test_class_terrain():
    assert is_surroundings(_table(ifc_class=["IfcGeographicElement"])).all()
    assert not is_surroundings(_table(ifc_class=["IfcWall"])).any()


def _scenario(n_house_walls: int, extra: list[tuple[float, float, bool]]):
    """Haus aus n_house_walls Wänden auf 10 × 10 m plus weitere Bauteile (x, y, on_site), Boxen 2 × 2 m."""
    rows = [(1000.0 + 8000 * (i % 2), 1000.0 + 8000 * (i // 2 % 2), False) for i in range(n_house_walls)] + extra
    return pd.DataFrame({"name": "Bauteil", "type_name": "", "layer": "", "is_printed": True,
                         "on_site": [z[2] for z in rows], "center_x_mm": [z[0] for z in rows],
                         "center_y_mm": [z[1] for z in rows], "bbox_x_mm": 2000.0, "bbox_y_mm": 2000.0})


def test_site_only_outside_the_building():
    """Ein Dach, das das Autorentool direkt ins Grundstück legt, bleibt Gebäude; eine Mauer daneben nicht."""
    df = _scenario(8, [(5000.0, 5000.0, True), (30000.0, 5000.0, True)])
    assert is_surroundings(df).tolist() == [False] * 8 + [False, True]


def test_outlier_far_away():
    from core.analysis.surroundings import outlier
    df = _scenario(8, [(800_000.0, 5000.0, False), (30_000.0, 5000.0, False)])
    assert outlier(df).tolist() == [False] * 8 + [True, False]      # 800 m weg: ja, Nachbar 30 m: nein
    assert not outlier(df.assign(is_printed=False)).any()
