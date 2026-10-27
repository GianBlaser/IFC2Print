"""Tests für die Datenbank-Schicht."""

import sqlite3

import pytest

from core.analysis.ruleset import Ruleset, ScaleParameters, seed_rules
from db.database import Database


@pytest.fixture
def file_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def db(file_path):
    database = Database(file_path)
    yield database
    database.close()


def _actions(db, ruleset_name):
    return {r["ifc_class_name"]: r["action"] for r in db.rules(ruleset_name)}


def test_seed_complete(db):
    assert db.rule_sets() == ["1:500", "1:200", "1:100", "1:50"]
    for m in db.rule_sets():
        assert _actions(db, m) == {z["ifc_class_name"]: z["action"] for z in seed_rules(m)}
        # inkl. IfcFooting (Fundament); ausser 1:50 auch IfcBeam.LINTEL (Storenkasten-Einlage als Quader)
        assert "IfcFooting" in _actions(db, m) and ("IfcBeam.LINTEL" in _actions(db, m)) == (m != "1:50")
    assert any(p["name"] == "Prusa MK4" for p in db.profiles())
    assert any(m["name"] == "PLA" for m in db.materials())


def test_rules_fields(db):
    rule = next(r for r in db.rules("1:200") if r["ifc_class_name"] == "IfcSlab")
    assert rule == {"ifc_class_name": "IfcSlab", "action": "behalten", "category": "Decke"}


def test_default_rule_content(db):
    rules = _actions(db, "1:200")
    assert rules["IfcWall"] == "behalten"
    assert rules["IfcDoor"] == "entfernen"
    assert rules["IfcColumn"] == "verdicken"
    assert rules["IfcCovering"] == "entfernen"
    assert rules["IfcCovering.CLADDING"] == "behalten"
    assert rules["IfcBeam.LINTEL"] == "fuellen"
    assert "IfcBeam.LINTEL" not in _actions(db, "1:50")          # 1:50: Storenkasten-Rinne als Detail behalten


def test_volume_rule_set_without_stairs(db):
    rules = _actions(db, "1:500")
    assert rules["IfcStair"] == "entfernen"
    assert rules["IfcStairFlight"] == "entfernen"
    assert rules["IfcRailing"] == "entfernen"


def test_railing_band_and_new_classes(db):
    for m in ("1:200", "1:100", "1:50"):
        rules = _actions(db, m)
        assert rules["IfcRailing"] == "band"
        assert rules["IfcRamp"] == "behalten" and rules["IfcChimney"] == "verdicken"
    assert _actions(db, "1:100")["IfcCovering.ROOFING"] == "behalten"
    assert _actions(db, "1:200")["IfcCovering.ROOFING"] == "entfernen"
    db.set_action("1:200", "IfcWall", "band")                      # «band» ist erlaubt
    assert _actions(db, "1:200")["IfcWall"] == "band"


def test_scale_parameters(db):
    from core.analysis.ruleset import ScaleParameters
    p500 = ScaleParameters.from_row(db.scale_parameters("1:500"))
    assert p500.min_thickness_wall_mm == 0.8 and p500.min_thickness_railing_mm is None
    assert p500.qualities == ("fein",) and not p500.connectors_allowed
    p50 = ScaleParameters.from_row(db.scale_parameters("1:50"))
    assert p50.reveal_depth_mm == 1.6 and p50.quality_default == "auto"
    assert ScaleParameters.from_row(db.scale_parameters("1:200")) == ScaleParameters.default("1:200")


def test_reset_rules(db):
    db.set_action("1:200", "IfcWall", "entfernen")
    db.set_action("1:200", "IfcFantasie", "fuellen")
    db.set_action("1:500", "IfcWall", "entfernen")
    db.reset_rules("1:200")
    rules = _actions(db, "1:200")
    assert rules["IfcWall"] == "behalten" and "IfcFantasie" not in rules
    assert _actions(db, "1:500")["IfcWall"] == "entfernen"           # andere Massstäbe unberührt


def test_migration_legacy_rule_sets(file_path):
    """DB von vor der Umstellung: alte Namen, CHECK ohne «band», eigene Regel und ein unbekanntes Set."""
    conn = sqlite3.connect(str(file_path))
    conn.execute("CREATE TABLE regel (id INTEGER PRIMARY KEY AUTOINCREMENT, regelset TEXT NOT NULL, "
                 "ifc_klasse TEXT NOT NULL, aktion TEXT NOT NULL CHECK (aktion IN ('behalten', 'verdicken', "
                 "'fuellen', 'entfernen')), kategorie TEXT NOT NULL, UNIQUE (regelset, ifc_klasse))")
    conn.executemany("INSERT INTO regel (regelset, ifc_klasse, aktion, kategorie) VALUES (?, ?, ?, ?)", [
        ("Standard 1:200", "IfcWall", "verdicken", "Wand"),              # Benutzerentscheid
        ("Standard 1:200", "IfcRailing", "entfernen", "Geländer"),       # alter Standard
        ("Volumen 1:500", "IfcSlab", "entfernen", "Decke"),
        ("Mein Set", "IfcWall", "behalten", "Wand")])
    conn.commit()
    conn.close()
    db = Database(file_path)
    assert _actions(db, "1:200")["IfcWall"] == "verdicken"
    assert _actions(db, "1:200")["IfcRailing"] == "band"
    assert _actions(db, "1:500")["IfcSlab"] == "entfernen"
    assert _actions(db, "1:200")["IfcRamp"] == "behalten"            # aus dem Seed ergänzt
    assert db.rules("Mein Set") == [] and db.rules("Standard 1:200") == []
    db.set_action("1:200", "IfcColumn", "band")                    # neuer CHECK greift
    db.close()


def test_set_action_persists(db, file_path):
    db.set_action("1:200", "IfcWall", "entfernen")
    assert _actions(db, "1:200")["IfcWall"] == "entfernen"
    db.close()
    db2 = Database(file_path)
    assert _actions(db2, "1:200")["IfcWall"] == "entfernen"
    db2.close()


def test_set_action_invalid(db):
    with pytest.raises(ValueError):
        db.set_action("1:200", "IfcWall", "is_printed")
    assert _actions(db, "1:200")["IfcWall"] == "behalten"


def test_set_action_creates_new_rule(db):
    db.set_action("1:200", "IfcFantasie", "fuellen", "Test")
    rule = next(r for r in db.rules("1:200") if r["ifc_class_name"] == "IfcFantasie")
    assert rule["action"] == "fuellen"
    assert rule["category"] == "Test"


def test_set_action_keeps_category(db):
    db.set_action("1:200", "IfcWall", "verdicken", "Andere")
    rule = next(r for r in db.rules("1:200") if r["ifc_class_name"] == "IfcWall")
    assert rule["action"] == "verdicken"
    assert rule["category"] == "Wand"


def test_second_open_duplicates_nothing(db, file_path):
    count = (len(db.rules("1:200")), len(db.profiles()), len(db.materials()))
    db.close()
    db2 = Database(file_path)
    assert (len(db2.rules("1:200")), len(db2.profiles()), len(db2.materials())) == count
    db2.close()


def test_second_open_keeps_user_changes(db, file_path):
    db.set_action("1:200", "IfcDoor", "fuellen")
    db.close()
    db2 = Database(file_path)
    assert _actions(db2, "1:200")["IfcDoor"] == "fuellen"
    db2.close()


def test_missing_seed_rule_is_added(db, file_path):
    with db._lock, db._conn:
        db._conn.execute("DELETE FROM rule WHERE ifc_class_name = 'IfcSlab'")
    db.close()
    db2 = Database(file_path)
    assert _actions(db2, "1:200")["IfcSlab"] == "behalten"
    db2.close()


def test_migration_printed_becomes_keep(file_path):
    """Alte DB ohne CHECK-Constraint mit Aktion «drucken» wird beim Öffnen migriert."""
    conn = sqlite3.connect(str(file_path))
    conn.execute("CREATE TABLE regel (id INTEGER PRIMARY KEY AUTOINCREMENT, regelset TEXT NOT NULL, "
                 "ifc_klasse TEXT NOT NULL, aktion TEXT NOT NULL, kategorie TEXT NOT NULL, "
                 "UNIQUE (regelset, ifc_klasse))")
    conn.execute("INSERT INTO regel (regelset, ifc_klasse, aktion, kategorie) "
                 "VALUES ('Standard 1:200', 'IfcWall', 'drucken', 'Wand')")
    conn.commit()
    conn.close()
    db = Database(file_path)
    assert _actions(db, "1:200")["IfcWall"] == "behalten"
    assert all(a != "drucken" for a in _actions(db, "1:200").values())
    db.close()


def test_schema_rejects_invalid_action(db):
    with pytest.raises(sqlite3.IntegrityError):
        with db._lock, db._conn:
            db._conn.execute("INSERT INTO rule (ruleset_name, ifc_class_name, action, category) "
                             "VALUES ('X', 'IfcWall', 'drucken', 'Wand')")


def test_write_and_read_export_run(db):
    new_id = db.write_export_run({
        "ifc_name": "test.ifc", "scale": 200, "ruleset_name": "1:200",
        "window_fill": 0, "part_count": 42, "filament_g": 12.3,
        "time_h": 1.5, "cost_chf": 0.31,
    })
    assert new_id == 1
    runs = db.export_runs()
    assert len(runs) == 1
    assert runs[0]["ifc_name"] == "test.ifc"
    assert runs[0]["date"]


def test_export_runs_newest_first(db):
    for name in ("a.ifc", "b.ifc"):
        db.write_export_run({"ifc_name": name, "scale": 200, "ruleset_name": "1:200"})
    assert [l["ifc_name"] for l in db.export_runs()] == ["b.ifc", "a.ifc"]


def test_migration_new_columns_in_export_run(file_path):
    """Alte regeln.db: fenster, tuer, element_count werden beim Öffnen ergänzt, alte Einträge bleiben."""
    conn = sqlite3.connect(str(file_path))
    conn.execute("CREATE TABLE exportlauf (id INTEGER PRIMARY KEY AUTOINCREMENT, datum TEXT NOT NULL, "
                 "ifc_name TEXT NOT NULL, massstab INTEGER NOT NULL, profil_id INTEGER, regelset TEXT NOT NULL, "
                 "modus TEXT, fenster_fuellen INTEGER NOT NULL DEFAULT 0, anzahl_teile INTEGER, "
                 "filament_g REAL, zeit_h REAL, kosten_chf REAL)")
    conn.execute("INSERT INTO exportlauf (datum, ifc_name, massstab, regelset) VALUES ('2026-01-01', 'alt.ifc', 200, 'x')")
    conn.commit()
    conn.close()
    db = Database(file_path)
    db.write_export_run({"ifc_name": "neu.ifc", "scale": 200, "ruleset_name": "x", "windows": "vertieft",
                             "doors": "geschlossen", "part_count": 5, "element_count": 120})
    runs = db.export_runs()
    assert runs[0]["windows"] == "vertieft" and runs[0]["element_count"] == 120
    assert runs[1]["ifc_name"] == "alt.ifc" and runs[1]["windows"] is None
    db.close()


def test_clearance_mm_seed_and_migration(file_path):
    """Neue DB: Prusa MK4 hat clearance_mm 0.20; alte printer_profile ohne Spalte wird ergänzt (Default 0.20)."""
    conn = sqlite3.connect(str(file_path))
    conn.execute("CREATE TABLE drucker_profil (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, "
                 "duese_mm REAL NOT NULL, layer_hoehe_mm REAL NOT NULL, bauraum_x_mm REAL NOT NULL, "
                 "bauraum_y_mm REAL NOT NULL, bauraum_z_mm REAL NOT NULL, mindestwand_mm REAL NOT NULL)")
    conn.execute("INSERT INTO drucker_profil (name, duese_mm, layer_hoehe_mm, bauraum_x_mm, bauraum_y_mm, "
                 "bauraum_z_mm, mindestwand_mm) VALUES ('Alt', 0.4, 0.2, 100, 100, 100, 0.8)")
    conn.commit()
    conn.close()
    db = Database(file_path)
    profiles = {p["name"]: p for p in db.profiles()}
    assert profiles["Alt"]["clearance_mm"] == 0.20
    assert profiles["Prusa MK4"]["clearance_mm"] == 0.20
    db.close()


def test_german_database_is_migrated_to_english(file_path):
    """Eine regeln.db von vor Oktober 2026 (deutsche Tabellen und Spalten) behält eigene Regeln und Verlauf."""
    conn = sqlite3.connect(str(file_path))
    conn.execute("CREATE TABLE regel (id INTEGER PRIMARY KEY AUTOINCREMENT, regelset TEXT NOT NULL, "
                 "ifc_klasse TEXT NOT NULL, aktion TEXT NOT NULL CHECK (aktion IN ('behalten', 'verdicken', "
                 "'fuellen', 'band', 'entfernen')), kategorie TEXT NOT NULL, UNIQUE (regelset, ifc_klasse))")
    conn.execute("INSERT INTO regel (regelset, ifc_klasse, aktion, kategorie) VALUES ('1:200', 'IfcWall', 'entfernen', 'Wand')")
    conn.execute("CREATE TABLE exportlauf (id INTEGER PRIMARY KEY AUTOINCREMENT, datum TEXT NOT NULL, ifc_name TEXT NOT NULL, "
                 "massstab INTEGER NOT NULL, profil_id INTEGER, regelset TEXT NOT NULL, modus TEXT)")
    conn.execute("INSERT INTO exportlauf (datum, ifc_name, massstab, regelset) VALUES ('2026-10-01', 'alt.ifc', 200, '1:200')")
    conn.commit()
    conn.close()
    db = Database(file_path)
    assert {r["ifc_class_name"]: r["action"] for r in db.rules("1:200")}["IfcWall"] == "entfernen"
    run = db.export_runs()[0]
    assert run["ifc_name"] == "alt.ifc" and run["scale"] == 200 and run["ruleset_name"] == "1:200"
    db.close()


def test_scale_parameters_follow_the_seed(file_path):
    """Die Massstab-Parameter kommen bei jedem Start aus massstaebe.csv – eine ältere Datenbank behält keine alten Werte."""
    db = Database(file_path)
    with db._lock, db._conn:
        db._conn.execute("UPDATE scale SET min_thickness_wall_mm = 9.9 WHERE ruleset_name = '1:200'")
    db.close()
    db = Database(file_path)
    assert db.scale_parameters("1:200")["min_thickness_wall_mm"] == ScaleParameters.default("1:200").min_thickness_wall_mm
    db.close()


def test_seed_skips_only_the_reason_column(db, tmp_path):
    """Nur «reason» gibt es bloss in der CSV; jede andere fehlende Spalte scheitert laut (_add_columns vergessen)."""
    seed = tmp_path / "material.csv"
    seed.write_text("name,density_g_cm3,price_chf_kg,reason\nTest-PLA,1.24,25.0,Begründung\n", encoding="utf-8")
    db._seed("material", seed)
    assert "Test-PLA" in {m["name"] for m in db.materials()}
    seed.write_text("name,density_g_cm3,price_chf_kg,unbekannt\nTest-PETG,1.27,28.0,x\n", encoding="utf-8")
    with pytest.raises(sqlite3.OperationalError):
        db._seed("material", seed)


def test_retired_standard_rule_is_removed_unless_changed(file_path):
    """IfcFlowTerminal → entfernen war Standard bis Okt. 2026 (heute IfcDistributionElement): unverändert gelöscht,
    vom Nutzer geändert bleibt sie als eigene Regel."""
    db = Database(file_path)
    db.set_action("1:200", "IfcFlowTerminal", "entfernen", "Haustechnik")
    db.set_action("1:100", "IfcFlowTerminal", "behalten", "Haustechnik")
    db.close()
    db = Database(file_path)
    assert "IfcFlowTerminal" not in {r["ifc_class_name"] for r in db.rules("1:200")}
    assert {r["ifc_class_name"]: r["action"] for r in db.rules("1:100")}["IfcFlowTerminal"] == "behalten"
    assert {r["ifc_class_name"]: r["action"] for r in db.rules("1:200")}["IfcDistributionElement"] == "entfernen"
    db.close()


# --- Bedingungen im Regelschlüssel ---

def test_set_action_with_condition_stores_the_key(db):
    db.set_action("1:200", "IfcCovering[aussen]", "behalten", "Fassade")
    rule = next(r for r in db.rules("1:200") if r["ifc_class_name"] == "IfcCovering[aussen]")
    assert rule == {"ifc_class_name": "IfcCovering[aussen]", "action": "behalten", "category": "Fassade"}
    assert _actions(db, "1:200")["IfcCovering"] == "entfernen"                       # Regel ohne Bedingung bleibt
    assert "IfcCovering[aussen]" not in _actions(db, "1:100")                        # andere Massstäbe unberührt
    ruleset = Ruleset.from_rows(db.rules("1:200"))
    assert ruleset.rule_source("IfcCovering", element={"is_external": True}) == "IfcCovering[aussen]"
    assert ruleset.rule_source("IfcCovering", element={"is_external": False}) == "IfcCovering"


def test_set_action_with_condition_updates_and_keeps_category(db):
    db.set_action("1:200", "IfcMember[duenner_als:0.8]", "entfernen", "Verglasung")
    db.set_action("1:200", "IfcMember[duenner_als:0.8]", "behalten", "Andere")
    rules = [r for r in db.rules("1:200") if r["ifc_class_name"] == "IfcMember[duenner_als:0.8]"]
    assert rules == [{"ifc_class_name": "IfcMember[duenner_als:0.8]", "action": "behalten", "category": "Verglasung"}]


def test_conditional_rule_survives_reopen(db, file_path):
    db.set_action("1:200", "IfcWall[tragend]", "verdicken", "Wand")
    db.close()
    db2 = Database(file_path)
    assert _actions(db2, "1:200")["IfcWall[tragend]"] == "verdicken"
    assert _actions(db2, "1:200")["IfcWall"] == "behalten"
    db2.close()


@pytest.mark.parametrize("key", ["IfcWall[unbekannt]", "IfcMember[duenner_als]", "IfcMember[duenner_als:abc]",
                                 "IfcMember[duenner_als:0]", "IfcWall[aussen:1]"])
def test_set_action_with_invalid_condition_stores_nothing(db, key):
    before = db.rules("1:200")
    with pytest.raises(ValueError):
        db.set_action("1:200", key, "behalten", "Wand")
    assert db.rules("1:200") == before


def test_delete_rule_removes_only_that_key(db):
    db.set_action("1:200", "IfcWall[aussen]", "verdicken", "Wand")
    db.set_action("1:100", "IfcWall[aussen]", "verdicken", "Wand")
    before = _actions(db, "1:200")
    db.delete_rule("1:200", "IfcWall[aussen]")
    assert _actions(db, "1:200") == {k: a for k, a in before.items() if k != "IfcWall[aussen]"}
    assert _actions(db, "1:200")["IfcWall"] == "behalten"                            # Regel ohne Bedingung bleibt
    assert _actions(db, "1:100")["IfcWall[aussen]"] == "verdicken"                   # anderer Massstab bleibt


def test_delete_rule_of_plain_key_keeps_conditional_key(db):
    db.set_action("1:200", "IfcFantasie", "fuellen", "Test")
    db.set_action("1:200", "IfcFantasie[innen]", "behalten", "Test")
    db.delete_rule("1:200", "IfcFantasie")
    rules = _actions(db, "1:200")
    assert "IfcFantasie" not in rules and rules["IfcFantasie[innen]"] == "behalten"


def test_delete_rule_of_unknown_key_changes_nothing(db):
    before = db.rules("1:200")
    db.delete_rule("1:200", "IfcWall[aussen]")
    db.delete_rule("1:333", "IfcWall")
    assert db.rules("1:200") == before
