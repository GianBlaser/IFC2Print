"""Tests für das Regelwerk."""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config import SCALES
from core.analysis.ruleset import (ACTIONS, ALL_SCALES, check_action, check_key, condition_label, condition_met,
                                   PRINTED_ACTIONS, row_scales, rule_class, rule_reason, Ruleset, ScaleParameters,
                                   scale_reason, seed_rules, split_key, _seed_rule_rows)
from core.ifc.schema import schema_wrapper
from core.openings.windows import OPENING_MODES
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


# --- Begründungen (Spalte «reason» der Seed-CSVs) ---------------------------------------------

@pytest.mark.parametrize("scale", list(SCALES))
def test_every_standard_rule_and_scale_has_a_reason(scale):
    ruleset_obj = Ruleset.default(scale)
    assert all(ruleset_obj.reason(k) for k in ruleset_obj.rules)
    assert scale_reason(scale)


def test_reason_follows_the_standard_only():
    """Die Begründung gilt nur, solange die Regel dem Standard entspricht."""
    standard = rule_reason("1:200", "IfcRailing", "band")
    assert standard and not standard.startswith("Eigene Regel")
    assert rule_reason("1:200", "IfcRailing", "entfernen") == "Eigene Regel (Standard: band)."
    assert rule_reason("1:200", "IfcFantasieElement", "behalten") == "Eigene Regel."
    assert rule_reason("1:200", "", "entfernen") == ""


def test_classify_adds_reason(ruleset_obj):
    out = ruleset_obj.classify(pd.DataFrame({"ifc_class": ["IfcWall", "IfcFantasieElement"]}))
    assert out["reason"].iloc[0] == ruleset_obj.reason("IfcWall") != ""
    assert out["reason"].iloc[1] == ""


def test_reason_stays_out_of_the_database(tmp_path):
    """Die Seed-Spalte «reason» hat in der Datenbank kein Gegenstück und wird beim Einspielen übergangen."""
    db = Database(tmp_path / "test.db")
    assert "reason" not in db.rules("1:200")[0]
    assert "reason" not in db.scale_parameters("1:200")
    db.close()


# --- Seed-Daten ---

CORE_KEYS = ("IfcWall", "IfcSlab", "IfcRoof", "IfcWindow", "IfcDoor")


def _in_ifc_schema(name: str) -> bool:
    """IFC-Klasse in mindestens einem der Schemas."""
    for schema in ("IFC2X3", "IFC4", "IFC4X3_ADD2"):
        try:
            schema_wrapper.schema_by_name(schema).declaration_by_name(name)
            return True
        except (RuntimeError, ValueError, KeyError):
            continue
    return False


@pytest.mark.parametrize("scale", SCALES)
def test_seed_actions_are_known(scale):
    """Jede Aktion der Seed-Regeln ist eine erlaubte Aktion."""
    rules = Ruleset.default(scale).rules
    assert rules
    assert {key: a for key, a in rules.items() if a not in ACTIONS} == {}


@pytest.mark.parametrize("scale", SCALES)
def test_seed_rules_have_reason(scale):
    """Jede Regel hat eine Begründung (keine leere, kein «Eigene Regel»)."""
    ruleset = Ruleset.default(scale)
    bad = [key for key in ruleset.rules
           if not ruleset.reason(key).strip() or ruleset.reason(key).startswith("Eigene Regel")]
    assert bad == []


@pytest.mark.parametrize("scale", SCALES)
def test_seed_rules_have_category(scale):
    """Jede Regel hat eine Kategorie."""
    ruleset = Ruleset.default(scale)
    assert [key for key in ruleset.rules if not ruleset.categories.get(key, "").strip()] == []


@pytest.mark.parametrize("scale", SCALES)
def test_seed_class_names_exist_in_schema(scale):
    """Alle IFC-Klassen in den Regelschlüsseln («Klasse», «Klasse.TYP», «Ganzes/Teil») gibt es in einem Schema."""
    unknown = [key for key in Ruleset.default(scale).rules
               if not all(_in_ifc_schema(part.split(".")[0]) for part in key.split("/"))]
    assert unknown == []


@pytest.mark.parametrize("scale", SCALES)
def test_seed_contains_core_keys(scale):
    """Jeder Massstab regelt mindestens Wand, Decke, Dach, Fenster und Tür."""
    assert set(CORE_KEYS) <= set(Ruleset.default(scale).rules)


@pytest.mark.parametrize("scale", SCALES)
def test_seed_scale_parameters_plausible(scale):
    """Massstabsparameter: Nenner passt zum Namen, Masse positiv, Standardwerte erlaubt."""
    p = ScaleParameters.default(scale)
    assert p.denominator == int(re.fullmatch(r"1:(\d+)", scale).group(1))
    assert p.reveal_depth_mm > 0
    assert p.min_core_reveal_mm > 0
    assert p.min_thickness_wall_mm >= p.min_core_reveal_mm
    assert p.quality_default in p.qualities
    assert p.window_default in OPENING_MODES
    assert p.door_default in OPENING_MODES
    assert scale_reason(scale).strip()


def test_seed_rows_name_known_scales():
    """Spalte «scales»: «alle» oder bekannte Massstäbe, keiner doppelt."""
    for row in _seed_rule_rows():
        scales = row_scales(row)
        assert len(scales) == len(set(scales)), row


def test_seed_deviation_differs_from_base():
    """Eine Abweichung ändert Aktion, Kategorie oder Begründung – sonst gehört der Massstab in die «alle»-Zeile."""
    base = {z["ifc_class_name"]: z for z in _seed_rule_rows() if z["scales"] == ALL_SCALES}
    fields = ("action", "category", "reason")
    same = [(z["scales"], z["ifc_class_name"]) for z in _seed_rule_rows()
            if z["scales"] != ALL_SCALES and z["ifc_class_name"] in base
            and all(z[f] == base[z["ifc_class_name"]][f] for f in fields)]
    assert same == []


def test_seed_rules_most_specific_row_wins(monkeypatch):
    """Die Zeile mit den wenigsten Massstäben gewinnt; zwei gleich spezifische Zeilen sind ein Fehler."""
    import core.analysis.ruleset as ruleset_module
    rows = ({"scales": "alle", "ifc_class_name": "IfcStair", "action": "behalten", "category": "Treppe", "reason": "a"},
            {"scales": "1:500", "ifc_class_name": "IfcStair", "action": "entfernen", "category": "Treppe", "reason": "b"})
    monkeypatch.setattr(ruleset_module, "_seed_rule_rows", lambda: rows)
    ruleset_module._seed_rules.cache_clear()
    try:
        assert [z["action"] for z in seed_rules("1:500")] == ["entfernen"]
        assert [z["action"] for z in seed_rules("1:200")] == ["behalten"]
        monkeypatch.setattr(ruleset_module, "_seed_rule_rows", lambda: rows + ({**rows[1], "action": "behalten"},))
        ruleset_module._seed_rules.cache_clear()
        with pytest.raises(ValueError, match="doppelt"):
            seed_rules("1:500")
    finally:
        ruleset_module._seed_rules.cache_clear()


# --- Bedingungen ---

def _classify(rules, columns, schema=None, scale="1:200", categories=None):
    """Kleine Bauteiltabelle mit einem Regelwerk aus ``rules`` klassifizieren."""
    return Ruleset(rules, categories, scale).classify(pd.DataFrame(columns), schema)


@pytest.mark.parametrize("key, expected", [
    ("IfcWall", ("IfcWall", "")),
    ("IfcWall[aussen]", ("IfcWall", "aussen")),
    ("IfcCovering.CLADDING[aussen]", ("IfcCovering.CLADDING", "aussen")),
    ("IfcMember[duenner_als:0.8]", ("IfcMember", "duenner_als:0.8")),
    ("IfcRoof/IfcMember[innen]", ("IfcRoof/IfcMember", "innen")),
])
def test_split_key(key, expected):
    assert split_key(key) == expected


def test_rule_class():
    assert rule_class("IfcCovering") == "IfcCovering"
    assert rule_class("IfcCovering.CLADDING") == "IfcCovering"
    assert rule_class("IfcCovering.CLADDING[aussen]") == "IfcCovering"
    assert rule_class("IfcWall[tragend]") == "IfcWall"
    assert rule_class("IfcRoof/IfcMember[innen]") == "IfcRoof/IfcMember"          # «Ganzes/Teil» bleibt


def test_condition_label():
    assert condition_label("duenner_als:0.8") == "dünner als 0.8 mm"
    assert [condition_label(c) for c in ("tragend", "aussen", "innen")] == ["tragend", "aussen", "innen"]


@pytest.mark.parametrize("key", ["IfcWall", "IfcWall[aussen]", "IfcWall[innen]", "IfcWall[tragend]",
                                 "IfcMember[duenner_als:0.8]", "IfcMember[duenner_als:2]",
                                 "IfcCovering.CLADDING[aussen]", "IfcRoof/IfcMember[innen]"])
def test_check_key_accepts_valid_keys(key):
    assert check_key(key) == key


@pytest.mark.parametrize("key", ["IfcWall[unbekannt]", "IfcMember[duenner_als]", "IfcMember[duenner_als:]",
                                 "IfcMember[duenner_als:abc]", "IfcMember[duenner_als:0]", "IfcMember[duenner_als:-1]",
                                 "IfcWall[aussen:1]", "IfcWall[tragend:ja]", "IfcMember[duenner_als:inf]",
                                 "IfcMember[duenner_als:nan]", "IfcWall[]", "IfcWall[aussen", "IfcWall[aussen]x"])
def test_check_key_rejects_invalid_conditions(key):
    with pytest.raises(ValueError):
        check_key(key)


def test_ruleset_rejects_unknown_condition():
    with pytest.raises(ValueError, match="Unbekannte Bedingung"):
        Ruleset({"IfcWall[unbekannt]": "behalten"}, {})
    with pytest.raises(ValueError):
        Ruleset({"IfcMember[duenner_als:abc]": "behalten"}, {})


def test_condition_met():
    assert condition_met("aussen", {"is_external": True})
    assert not condition_met("aussen", {"is_external": False})
    assert not condition_met("aussen", {"is_external": None}) and not condition_met("aussen", {})
    assert condition_met("innen", {"is_external": False})
    assert not condition_met("innen", {"is_external": True})
    assert not condition_met("innen", {"is_external": None}) and not condition_met("innen", {})
    assert condition_met("tragend", {"load_bearing": True})
    assert not condition_met("tragend", {"load_bearing": False}) and not condition_met("tragend", {})
    assert condition_met("duenner_als:0.8", {"thickness_model_mm": 0.5})
    assert not condition_met("duenner_als:0.8", {"thickness_model_mm": 0.8})           # echt kleiner
    assert not condition_met("duenner_als:0.8", {"thickness_model_mm": float("nan")})
    assert not condition_met("duenner_als:0.8", {"thickness_model_mm": None}) and not condition_met("duenner_als:0.8", {})


def test_condition_aussen_and_innen_with_fallback():
    """«innen» trifft nur bei IsExternal = False; fehlt die Angabe, gilt der Schlüssel ohne Bedingung."""
    external = [True, False, None]
    out = _classify({"IfcWall": "entfernen", "IfcWall[aussen]": "behalten"},
                    {"ifc_class": ["IfcWall"] * 3, "is_external": external})
    assert list(out["rule"]) == ["IfcWall[aussen]", "IfcWall", "IfcWall"]
    assert list(out["action"]) == ["behalten", "entfernen", "entfernen"]
    assert list(out["is_printed"]) == [True, False, False]
    out = _classify({"IfcWall": "behalten", "IfcWall[innen]": "entfernen"},
                    {"ifc_class": ["IfcWall"] * 3, "is_external": external})
    assert list(out["rule"]) == ["IfcWall", "IfcWall[innen]", "IfcWall"]
    assert list(out["action"]) == ["behalten", "entfernen", "behalten"]


def test_condition_tragend():
    out = _classify({"IfcWall": "behalten", "IfcWall[tragend]": "verdicken"},
                    {"ifc_class": ["IfcWall"] * 3, "load_bearing": [True, False, None]})
    assert list(out["rule"]) == ["IfcWall[tragend]", "IfcWall", "IfcWall"]
    assert list(out["action"]) == ["verdicken", "behalten", "behalten"]


@pytest.mark.parametrize("scale, thickness, expected", [
    ("1:200", [100.0, 159.0, 160.0, 200.0], [True, True, False, False]),           # 100 mm real = 0.5 mm Modell
    ("1:100", [40.0, 79.0, 80.0, 100.0], [True, True, False, False]),
    ("1:50", [20.0, 39.0, 40.0, 100.0], [True, True, False, False]),
    ("1:500", [200.0, 399.0, 400.0, 1000.0], [True, True, False, False]),
])
def test_condition_thinner_than_uses_model_thickness(scale, thickness, expected):
    """Dicke am Modell = thickness_min_mm geteilt durch den Nenner des Massstabs; Grenzwert ist exklusiv."""
    rules = {"IfcMember": "behalten", "IfcMember[duenner_als:0.8]": "entfernen"}
    out = _classify(rules, {"ifc_class": ["IfcMember"] * 4, "thickness_min_mm": thickness}, scale=scale)
    assert [r == "IfcMember[duenner_als:0.8]" for r in out["rule"]] == expected
    assert [a == "entfernen" for a in out["action"]] == expected


def test_condition_thinner_than_uses_parameter_denominator():
    rules = {"IfcMember": "behalten", "IfcMember[duenner_als:0.8]": "entfernen"}
    df = pd.DataFrame({"ifc_class": ["IfcMember"], "thickness_min_mm": [100.0]})
    assert Ruleset(rules, {}, "1:200").parameter.denominator == 200
    assert Ruleset(rules, {}, "1:200").classify(df).loc[0, "rule"] == "IfcMember[duenner_als:0.8]"      # 0.5 mm
    assert Ruleset(rules, {}, "1:100").classify(df).loc[0, "rule"] == "IfcMember"                       # 1.0 mm
    parameter = ScaleParameters(denominator=1000)
    assert Ruleset(rules, {}, "1:200", parameter).classify(df).loc[0, "rule"] == "IfcMember[duenner_als:0.8]"


def test_condition_thinner_than_without_thickness_falls_back():
    """Ohne Geometrie (NaN) trifft «duenner_als» nie zu."""
    out = _classify({"IfcMember": "behalten", "IfcMember[duenner_als:0.8]": "entfernen"},
                    {"ifc_class": ["IfcMember"] * 2, "thickness_min_mm": [np.nan, 100.0]})
    assert list(out["rule"]) == ["IfcMember", "IfcMember[duenner_als:0.8]"]


def test_condition_is_inherited_by_subclass():
    """IfcWallStandardCase hat keine eigene Regel und erbt auch die bedingte Regel von IfcWall."""
    rules = {"IfcWall": "behalten", "IfcWall[aussen]": "verdicken"}
    columns = {"ifc_class": ["IfcWallStandardCase"] * 3, "is_external": [True, False, None]}
    out = _classify(rules, columns, schema="IFC2X3")
    assert list(out["rule"]) == ["IfcWall[aussen]", "IfcWall", "IfcWall"]
    assert list(out["action"]) == ["verdicken", "behalten", "behalten"]
    assert list(_classify(rules, columns)["rule"]) == ["", "", ""]                 # ohne Schema keine Vererbung


def test_own_rule_of_subclass_beats_conditional_rule_of_parent():
    """Die Stufen der Vererbungskette gehen vor: die Regel der Unterklasse gewinnt gegen die bedingte der Oberklasse."""
    rules = {"IfcWall[aussen]": "verdicken", "IfcWallStandardCase": "behalten"}
    out = _classify(rules, {"ifc_class": ["IfcWallStandardCase"], "is_external": [True]}, schema="IFC2X3")
    assert out.loc[0, "rule"] == "IfcWallStandardCase"


def test_conditional_key_without_plain_key():
    """Gibt es nur die bedingte Regel, wird alles andere der Klasse entfernt."""
    out = _classify({"IfcWall[aussen]": "behalten"}, {"ifc_class": ["IfcWall"] * 3, "is_external": [True, False, None]})
    assert list(out["rule"]) == ["IfcWall[aussen]", "", ""]
    assert list(out["action"]) == ["behalten", "entfernen", "entfernen"]
    assert list(out["is_printed"]) == [True, False, False]


def test_predefined_type_beats_condition_on_class():
    """Klasse.TYP gewinnt gegen Klasse[Bedingung]: CLADDING bleibt «behalten», auch wenn «aussen» verdickt."""
    rules = {"IfcCovering": "entfernen", "IfcCovering.CLADDING": "behalten", "IfcCovering[aussen]": "verdicken"}
    out = _classify(rules, {"ifc_class": ["IfcCovering"] * 3, "predefined_type": ["CLADDING", "FLOORING", ""],
                            "is_external": [True, True, True]})
    assert list(out["rule"]) == ["IfcCovering.CLADDING", "IfcCovering[aussen]", "IfcCovering[aussen]"]
    assert list(out["action"]) == ["behalten", "verdicken", "verdicken"]


@pytest.mark.parametrize("predefined_type, external, expected", [
    ("CLADDING", True, "IfcCovering.CLADDING[aussen]"),
    ("CLADDING", False, "IfcCovering.CLADDING"),
    ("CLADDING", None, "IfcCovering.CLADDING"),
    ("FLOORING", True, "IfcCovering[aussen]"),
    ("FLOORING", False, "IfcCovering"),
    ("", True, "IfcCovering[aussen]"),
    ("", None, "IfcCovering"),
])
def test_precedence_within_one_level(predefined_type, external, expected):
    """Klasse.TYP[Bedingung] → Klasse.TYP → Klasse[Bedingung] → Klasse."""
    rules = {"IfcCovering": "entfernen", "IfcCovering[aussen]": "verdicken",
             "IfcCovering.CLADDING": "behalten", "IfcCovering.CLADDING[aussen]": "fuellen"}
    out = _classify(rules, {"ifc_class": ["IfcCovering"], "predefined_type": [predefined_type], "is_external": [external]})
    assert out.loc[0, "rule"] == expected
    assert out.loc[0, "action"] == rules[expected]


def test_predefined_type_with_condition_applies_only_when_met():
    """Ohne Spalte is_external bleibt auch Klasse.TYP[Bedingung] unwirksam."""
    rules = {"IfcCovering.CLADDING": "behalten", "IfcCovering.CLADDING[aussen]": "fuellen"}
    df = pd.DataFrame({"ifc_class": ["IfcCovering"], "predefined_type": ["CLADDING"]})
    assert Ruleset(rules).classify(df).loc[0, "rule"] == "IfcCovering.CLADDING"


def test_condition_order_follows_conditions():
    """Bei mehreren zutreffenden Bedingungen gewinnt die erste in CONDITIONS, unabhängig von der Reihenfolge der Regeln."""
    thin_external_bearing = {"is_external": True, "load_bearing": True, "thickness_model_mm": 0.5}
    thick_internal_bearing = {"is_external": False, "load_bearing": True, "thickness_model_mm": 2.0}
    order = ["IfcWall[duenner_als:0.8]", "IfcWall[tragend]", "IfcWall[aussen]"]
    for keys in (order, order[::-1]):
        for winner in range(len(order)):
            ruleset = Ruleset({"IfcWall": "behalten", **{k: "verdicken" for k in keys if k in order[winner:]}})
            assert ruleset.rule_source("IfcWall", element=thin_external_bearing) == order[winner]
    for keys in (["IfcWall[tragend]", "IfcWall[innen]"], ["IfcWall[innen]", "IfcWall[tragend]"]):
        ruleset = Ruleset({"IfcWall": "behalten", **{k: "verdicken" for k in keys}})
        assert ruleset.rule_source("IfcWall", element=thick_internal_bearing) == "IfcWall[tragend]"
    assert Ruleset({"IfcWall": "behalten", "IfcWall[innen]": "verdicken"}).rule_source(
        "IfcWall", element=thick_internal_bearing) == "IfcWall[innen]"


def test_thinner_than_beats_external_in_classify():
    rules = {"IfcWall": "behalten", "IfcWall[aussen]": "verdicken", "IfcWall[duenner_als:0.8]": "entfernen"}
    out = _classify(rules, {"ifc_class": ["IfcWall"] * 3, "is_external": [True, True, False],
                            "thickness_min_mm": [100.0, 400.0, 100.0]})
    assert list(out["rule"]) == ["IfcWall[duenner_als:0.8]", "IfcWall[aussen]", "IfcWall[duenner_als:0.8]"]


@pytest.mark.parametrize("keys", [("IfcMember[duenner_als:2]", "IfcMember[duenner_als:10]"),
                                  ("IfcMember[duenner_als:10]", "IfcMember[duenner_als:2]")])
def test_smaller_threshold_wins(keys):
    """Bei «duenner_als» gewinnt der kleinere Grenzwert (Zahl, nicht Text: 2 vor 10)."""
    out = _classify({"IfcMember": "behalten", **{k: "entfernen" for k in keys}},
                    {"ifc_class": ["IfcMember"] * 4, "thickness_min_mm": [100.0, 600.0, 4000.0, np.nan]})
    assert list(out["rule"]) == ["IfcMember[duenner_als:2]", "IfcMember[duenner_als:10]", "IfcMember", "IfcMember"]


def test_conditions_without_property_columns_use_plain_rule():
    """Fehlen is_external, load_bearing und thickness_min_mm in der Tabelle, trifft keine Bedingung zu."""
    rules = {"IfcWall": "behalten", "IfcWall[aussen]": "entfernen", "IfcWall[innen]": "entfernen",
             "IfcWall[tragend]": "entfernen", "IfcWall[duenner_als:0.8]": "entfernen"}
    out = _classify(rules, {"ifc_class": ["IfcWall"] * 2})
    assert list(out["rule"]) == ["IfcWall", "IfcWall"]
    assert list(out["action"]) == ["behalten", "behalten"]


def test_conditions_read_only_the_present_columns():
    rules = {"IfcWall": "behalten", "IfcWall[aussen]": "verdicken", "IfcWall[tragend]": "entfernen"}
    out = _classify(rules, {"ifc_class": ["IfcWall"] * 2, "is_external": [True, False]})        # kein load_bearing
    assert list(out["rule"]) == ["IfcWall[aussen]", "IfcWall"]


def test_rule_source_without_element_uses_plain_rule():
    ruleset = Ruleset({"IfcWall": "behalten", "IfcWall[aussen]": "verdicken"})
    assert ruleset.rule_source("IfcWall") == "IfcWall"
    assert ruleset.action("IfcWall") == "behalten"
    assert ruleset.action("IfcWall", element={"is_external": True}) == "verdicken"
    assert ruleset.category("IfcWall", element={"is_external": True}) == "Sonstiges"


def test_condition_on_aggregate_key():
    """«Ganzes/Teil[Bedingung]» gilt nur für Teile, die sie erfüllen; die übrigen folgen dem Ganzen."""
    rules = {"IfcRoof": "behalten", "IfcRoof/IfcMember[innen]": "entfernen"}
    columns = {"ifc_class": ["IfcMember"] * 3, "aggregate": ["IfcRoof"] * 3, "is_external": [False, True, None]}
    out = _classify(rules, columns, schema="IFC4")
    assert list(out["rule"]) == ["IfcRoof/IfcMember[innen]", "IfcRoof", "IfcRoof"]
    assert list(out["action"]) == ["entfernen", "behalten", "behalten"]
    rules = {**rules, "IfcRoof/IfcMember": "fuellen"}
    out = _classify(rules, columns, schema="IFC4")
    assert list(out["rule"]) == ["IfcRoof/IfcMember[innen]", "IfcRoof/IfcMember", "IfcRoof/IfcMember"]


def test_condition_on_whole_of_aggregate():
    """Auch die Regel des Ganzen kann eine Bedingung haben (Eigenschaften des Teils)."""
    rules = {"IfcRoof": "behalten", "IfcRoof[aussen]": "verdicken"}
    out = _classify(rules, {"ifc_class": ["IfcPlate"] * 2, "aggregate": ["IfcRoof"] * 2, "is_external": [True, False]},
                    schema="IFC2X3")
    assert list(out["rule"]) == ["IfcRoof[aussen]", "IfcRoof"]


def test_conditional_key_outside_the_standard_is_own_rule():
    """Ein bedingter Schlüssel kommt nie aus der Seed-CSV: seine Begründung ist «Eigene Regel.»."""
    rows = [*seed_rules("1:200"), {"ifc_class_name": "IfcCovering[aussen]", "action": "behalten", "category": "Fassade"}]
    ruleset = Ruleset.from_rows(rows, "1:200")
    out = ruleset.classify(pd.DataFrame({"ifc_class": ["IfcCovering"] * 3, "is_external": [True, False, None]}))
    assert list(out["rule"]) == ["IfcCovering[aussen]", "IfcCovering", "IfcCovering"]
    assert out.loc[0, "reason"] == "Eigene Regel."
    assert out.loc[1, "reason"] == out.loc[2, "reason"] == ruleset.reason("IfcCovering") != ""
    assert not out.loc[1, "reason"].startswith("Eigene Regel")
    assert ruleset.reason("IfcCovering[aussen]") == "Eigene Regel."
    assert rule_reason("1:200", "IfcCovering[aussen]", "behalten") == "Eigene Regel."


def test_category_comes_from_the_conditional_key():
    categories = {"IfcCovering": "Ausbau", "IfcCovering[aussen]": "Fassade"}
    out = _classify({"IfcCovering": "entfernen", "IfcCovering[aussen]": "behalten"},
                    {"ifc_class": ["IfcCovering"] * 3, "is_external": [True, False, None]}, categories=categories)
    assert list(out["category"]) == ["Fassade", "Ausbau", "Ausbau"]
    ruleset = Ruleset({"IfcCovering": "entfernen", "IfcCovering[aussen]": "behalten"}, categories)
    assert ruleset.category("IfcCovering", element={"is_external": True}) == "Fassade"
    assert ruleset.category("IfcCovering", element={"is_external": False}) == "Ausbau"


def test_flag_accepts_numpy_and_missing_values():
    """Spalten aus numpy: bool-Spalte, np.bool_ in einer Objektspalte, Fliesskomma mit NaN."""
    rules = {"IfcWall": "behalten", "IfcWall[aussen]": "verdicken", "IfcWall[tragend]": "entfernen"}
    out = _classify(rules, {"ifc_class": ["IfcWall"] * 2, "is_external": np.array([True, False])})
    assert out["is_external"].dtype == bool
    assert list(out["rule"]) == ["IfcWall[aussen]", "IfcWall"]
    out = _classify(rules, {"ifc_class": ["IfcWall"] * 4,
                            "is_external": pd.Series([np.True_, np.False_, None, np.nan], dtype=object)})
    assert list(out["rule"]) == ["IfcWall[aussen]", "IfcWall", "IfcWall", "IfcWall"]
    out = _classify(rules, {"ifc_class": ["IfcWall"] * 3, "load_bearing": np.array([1.0, 0.0, np.nan])})
    assert list(out["rule"]) == ["IfcWall[tragend]", "IfcWall", "IfcWall"]
    out = _classify(rules, {"ifc_class": ["IfcWall"] * 3,
                            "is_external": pd.array([True, False, None], dtype="boolean")})   # pd.NA
    assert list(out["rule"]) == ["IfcWall[aussen]", "IfcWall", "IfcWall"]


def test_flag_innen_ignores_missing_values_in_numpy_columns():
    rules = {"IfcWall": "behalten", "IfcWall[innen]": "entfernen"}
    out = _classify(rules, {"ifc_class": ["IfcWall"] * 4,
                            "is_external": pd.Series([np.True_, np.False_, None, np.nan], dtype=object)})
    assert list(out["rule"]) == ["IfcWall", "IfcWall[innen]", "IfcWall", "IfcWall"]


def test_ruleset_without_conditions_ignores_property_columns():
    ruleset = Ruleset({"IfcWall": "behalten"})
    base = pd.DataFrame({"ifc_class": ["IfcWall", "IfcDoor"]})
    extra = base.assign(is_external=["x", None], load_bearing=[None, "y"], thickness_min_mm=[100.0, np.nan])
    result = ruleset.classify(extra).drop(columns=["is_external", "load_bearing", "thickness_min_mm"])
    assert result.equals(ruleset.classify(base))


# --- Bedingungen: Eigenschaften aus dem IFC (core/ifc/table.py) ---

MFH_MODEL = Path(__file__).parent.parent / "testdaten" / "MFH_eBKPH_Test.ifc"


def _common_flags_of(ifc_class="IfcWall", pset_name="Pset_WallCommon", own=None, type_flags=None):
    """``_common_flags`` eines Bauteils in einer leeren IFC4-Datei; ``own``/``type_flags``: Eigenschaften von Bauteil/Typ."""
    import ifcopenshell
    import ifcopenshell.api.type as ifc_type
    from ifcopenshell.api import pset, root
    from core.ifc.table import _common_flags
    ifc_file = ifcopenshell.file(schema="IFC4")          # muss leben, solange das Bauteil benutzt wird
    element = root.create_entity(ifc_file, ifc_class=ifc_class)
    if type_flags is not None:
        element_type = root.create_entity(ifc_file, ifc_class=f"{ifc_class}Type")
        ifc_type.assign_type(ifc_file, related_objects=[element], relating_type=element_type)
        pset.edit_pset(ifc_file, pset=pset.add_pset(ifc_file, product=element_type, name=pset_name), properties=type_flags)
    if own is not None:
        pset.edit_pset(ifc_file, pset=pset.add_pset(ifc_file, product=element, name=pset_name), properties=own)
    return _common_flags(element)


def test_common_flags_from_pset():
    assert _common_flags_of(own={"IsExternal": True, "LoadBearing": False}) == {"is_external": True, "load_bearing": False}
    door = _common_flags_of("IfcDoor", "Pset_DoorCommon", own={"IsExternal": False})
    assert door == {"is_external": False, "load_bearing": None}


def test_common_flags_missing_are_none():
    assert _common_flags_of() == {"is_external": None, "load_bearing": None}
    assert _common_flags_of(own={"IsExternal": True}) == {"is_external": True, "load_bearing": None}
    assert _common_flags_of(own={"LoadBearing": True}) == {"is_external": None, "load_bearing": True}


def test_common_flags_inherited_from_type_but_occurrence_wins():
    assert _common_flags_of(type_flags={"IsExternal": True, "LoadBearing": True}) == \
        {"is_external": True, "load_bearing": True}
    both = _common_flags_of(own={"IsExternal": False}, type_flags={"IsExternal": True, "LoadBearing": True})
    assert both == {"is_external": False, "load_bearing": True}


def test_common_flags_ignore_other_psets_and_non_boolean_values():
    other = _common_flags_of(pset_name="Eigene_Werte", own={"IsExternal": True, "LoadBearing": True})
    assert other == {"is_external": None, "load_bearing": None}                          # kein Pset_…Common
    text = _common_flags_of(pset_name="Pset_EigeneCommon", own={"IsExternal": "ja", "LoadBearing": 1})
    assert text == {"is_external": None, "load_bearing": None}                           # kein Wahrheitswert


@pytest.fixture(scope="module")
def mfh_model():
    from core.ifc.model import IfcModel
    return IfcModel.open_file(MFH_MODEL)


@pytest.mark.skipif(not MFH_MODEL.exists(), reason="testdaten/ fehlt (nicht im Repo)")
def test_model_table_has_flags_and_conditions_apply(mfh_model):
    """IfcWall hat IsExternal und LoadBearing (wahr und falsch), IfcCovering keine; die Regeln folgen dem."""
    df = mfh_model.building_elements
    walls = df[df["ifc_class"] == "IfcWall"]
    assert set(walls["is_external"]) == {True, False}
    assert set(walls["load_bearing"]) == {True, False}
    coverings = df[df["ifc_class"] == "IfcCovering"]
    assert len(coverings) > 0
    assert coverings["is_external"].isna().all() and coverings["load_bearing"].isna().all()
    ruleset = Ruleset({"IfcWall": "behalten", "IfcWall[aussen]": "verdicken", "IfcCovering": "entfernen",
                       "IfcCovering[aussen]": "behalten"})
    out = ruleset.classify(df, mfh_model.schema)
    expected = walls["is_external"].map({True: "IfcWall[aussen]", False: "IfcWall"})
    assert list(out.loc[walls.index, "rule"]) == list(expected)
    assert set(out.loc[coverings.index, "rule"]) == {"IfcCovering"}                    # ohne IsExternal keine Bedingung
