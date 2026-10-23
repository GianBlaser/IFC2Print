"""Tests für das Regelwerk."""

import pandas as pd
import pytest

from core.analysis.ruleset import check_action, PRINTED_ACTIONS, Ruleset
from db.database import Database


@pytest.fixture(scope="module")
def ruleset_obj():
    return Ruleset.default()


def test_known_class_remove(ruleset_obj):
    assert ruleset_obj.action("IfcDoor") == "entfernen"


def test_known_class_keep(ruleset_obj):
    assert ruleset_obj.action("IfcWall") == "behalten"


def test_known_class_thicken(ruleset_obj):
    assert ruleset_obj.action("IfcColumn") == "verdicken"


def test_unknown_class_remove(ruleset_obj):
    """Unbekannte Klassen (z.B. Möblierungs-Unterklassen) werden nicht gedruckt."""
    assert ruleset_obj.action("IfcUnbekanntesElement") == "entfernen"


def test_printed_amount():
    assert PRINTED_ACTIONS == {"behalten", "verdicken", "fuellen", "band"}


def test_category(ruleset_obj):
    assert ruleset_obj.category("IfcSlab") == "Decke"
    assert ruleset_obj.category("IfcUnbekannt") == "Sonstiges"


def test_predefined_type_takes_precedence(ruleset_obj):
    assert ruleset_obj.action("IfcCovering") == "entfernen"
    assert ruleset_obj.action("IfcCovering", "CLADDING") == "behalten"
    assert ruleset_obj.category("IfcCovering", "CLADDING") == "Fassade"
    assert ruleset_obj.action("IfcCovering", "FLOORING") == "entfernen"
    assert ruleset_obj.category("IfcCovering", "FLOORING") == "Ausbau"


def test_classify_appends_columns(ruleset_obj):
    df = pd.DataFrame({"ifc_class": ["IfcWall", "IfcDoor", "IfcColumn"]})
    out = ruleset_obj.classify(df)
    assert list(out["is_printed"]) == [True, False, True]
    assert list(out["category"]) == ["Wand", "Öffnung", "Stütze"]
    assert list(out["action"]) == ["behalten", "entfernen", "verdicken"]
    assert "is_printed" not in df.columns


def test_classify_with_type_column(ruleset_obj):
    df = pd.DataFrame({"ifc_class": ["IfcCovering", "IfcCovering", "IfcWall"],
                       "predefined_type": ["CLADDING", "FLOORING", ""]})
    out = ruleset_obj.classify(df)
    assert list(out["action"]) == ["behalten", "entfernen", "behalten"]
    assert list(out["is_printed"]) == [True, False, True]


def test_classify_unknown_class_without_warning(ruleset_obj, recwarn):
    out = ruleset_obj.classify(pd.DataFrame({"ifc_class": ["IfcWall", "IfcFantasieElement"]}))
    assert out.loc[1, "action"] == "entfernen"
    assert not out.loc[1, "is_printed"]
    assert len(recwarn) == 0


def test_fill_is_printed():
    ruleset_obj = Ruleset({"IfcWindow": "fuellen"}, {"IfcWindow": "Öffnung"})
    out = ruleset_obj.classify(pd.DataFrame({"ifc_class": ["IfcWindow"]}))
    assert out.loc[0, "action"] == "fuellen"
    assert out.loc[0, "is_printed"]


def test_invalid_action_in_constructor():
    with pytest.raises(ValueError):
        Ruleset({"IfcWall": "is_printed"})


def test_check_action():
    assert check_action("behalten") == "behalten"
    with pytest.raises(ValueError):
        check_action("is_printed")


def test_empty_ruleset_without_fallback():
    """Ein leeres Regelwerk bleibt leer: alles wird entfernt, keine Defaults."""
    ruleset_obj = Ruleset({})
    assert ruleset_obj.rules == {}
    assert ruleset_obj.action("IfcWall") == "entfernen"
    assert ruleset_obj.category("IfcWall") == "Sonstiges"


def test_from_rows_of_db_identical_to_default(tmp_path, ruleset_obj):
    db = Database(tmp_path / "test.db")
    rw_db = Ruleset.from_rows(db.rules("1:200"))
    db.close()
    assert rw_db.rules == ruleset_obj.rules
    assert rw_db.categories == ruleset_obj.categories
    df = pd.DataFrame({"ifc_class": ["IfcWall", "IfcDoor", "IfcColumn", "IfcSlab", "IfcRailing", "IfcStair"]})
    assert rw_db.classify(df).equals(ruleset_obj.classify(df))


def test_volume_rule_set_without_stairs():
    ruleset_obj = Ruleset.default("1:500")
    assert ruleset_obj.action("IfcStair") == "entfernen"
    assert Ruleset.default().action("IfcStair") == "behalten"


# --- Vererbung und Aggregate (Analysebericht B-02, B-05) ------------------------

def test_subclass_inherits_rule_of_superclass(ruleset_obj):
    """IfcSlabStandardCase hat keine eigene Regel und wird wie IfcSlab gedruckt (früher still entfernt)."""
    assert ruleset_obj.action("IfcSlabStandardCase", schema="IFC4") == "behalten"
    assert ruleset_obj.category("IfcSlabStandardCase", schema="IFC4") == "Decke"
    assert ruleset_obj.action("IfcBeamStandardCase", schema="IFC4") == "verdicken"
    assert ruleset_obj.rule_source("IfcSlabStandardCase", schema="IFC4") == "IfcSlab"
    assert ruleset_obj.action("IfcSlabStandardCase") == "entfernen"          # ohne Schema keine Vererbung


def test_inheritance_with_predefined_type(ruleset_obj):
    assert ruleset_obj.action("IfcCovering", "CLADDING", "IFC4") == "behalten"
    assert ruleset_obj.action("IfcSlab", "", "IFC4X3_ADD2") == "behalten"


def test_unknown_schema_without_inheritance(ruleset_obj):
    assert ruleset_obj.action("IfcSlabStandardCase", schema="IFC99") == "entfernen"


def test_foundation_own_rule(ruleset_obj):
    assert ruleset_obj.action("IfcFooting", schema="IFC4") == "entfernen"
    assert ruleset_obj.category("IfcFooting", schema="IFC4") == "Fundament"
    assert ruleset_obj.rule_source("IfcFooting", schema="IFC4") == "IfcFooting"


def test_parts_follow_the_aggregate(ruleset_obj):
    """Platten und Pfosten eines Glasdachs werden mit dem Dach gedruckt, nicht als «Verglasung» entfernt."""
    assert ruleset_obj.action("IfcPlate", schema="IFC2X3") == "entfernen"
    assert ruleset_obj.action("IfcPlate", schema="IFC2X3", aggregate="IfcRoof") == "behalten"
    assert ruleset_obj.category("IfcMember", schema="IFC2X3", aggregate="IfcRoof") == "Dach"
    assert ruleset_obj.action("IfcMember", schema="IFC2X3", aggregate="IfcCurtainWall") == "entfernen"
    # Ganzes ohne Regel (Baugruppe): die Regel des Teils gilt
    assert ruleset_obj.action("IfcWall", schema="IFC4", aggregate="IfcElementAssembly") == "behalten"


def test_key_aggregate_part_takes_precedence():
    ruleset_obj = Ruleset({"IfcRoof": "behalten", "IfcRoof/IfcMember": "entfernen", "IfcMember": "behalten"})
    assert ruleset_obj.action("IfcMember", schema="IFC4", aggregate="IfcRoof") == "entfernen"
    assert ruleset_obj.action("IfcPlate", schema="IFC4", aggregate="IfcRoof") == "behalten"


def test_classify_with_schema_and_aggregate(ruleset_obj):
    df = pd.DataFrame({"ifc_class": ["IfcSlabStandardCase", "IfcPlate", "IfcFantasie"],
                       "predefined_type": ["", "", ""], "aggregate": ["", "IfcRoof", ""]})
    out = ruleset_obj.classify(df, "IFC4")
    assert list(out["is_printed"]) == [True, True, False]
    assert list(out["rule"]) == ["IfcSlab", "IfcRoof", ""]


def test_four_scales_with_parameters():
    for m, wall in (("1:500", 0.8), ("1:200", 1.2), ("1:100", 1.2), ("1:50", 1.2)):
        ruleset_obj = Ruleset.default(m)
        assert ruleset_obj.scale == m and ruleset_obj.parameter.min_thickness_wall_mm == wall
    assert Ruleset.default("1:200").action("IfcRailing") == "band"
    assert Ruleset.default("Standard 1:200").scale == "1:200"          # alter Name
    with pytest.raises(ValueError):
        Ruleset.default("1:333")
