"""Tests der Oberfläche: Sitzungszustand (ohne Browser) und NiceGUI-Seite (simulierter Nutzer)."""

import asyncio
import re
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from db.database import Database
from ui.state import Session

MFH = Path(__file__).parent.parent / "testdaten" / "Building-Architecture-IFC2x3.ifc"


@pytest.fixture
def session(tmp_path):
    s = Session(Database(tmp_path / "ui.db"))
    s.load_bytes(MFH.read_bytes(), MFH.name)
    return s


def test_setting_changes_analysis(session):
    """Massstab wechseln analysiert sofort neu – kein veralteter Zustand."""
    previous = session.df["thickness_model_mm"].copy()
    session.scale = "1:100"
    session.analyse()
    assert (session.df["thickness_model_mm"].dropna() == 2 * previous.dropna()).all()


def test_new_analysis_marks_result_stale(session):
    """Änderung → Ergebnis bleibt sichtbar, aber veraltet (Downloads gesperrt); neu erzeugen hebt das auf."""
    session.quality = "entwurf"
    e = session.generate()
    assert session.result is e and not session.stale
    assert session.db.export_runs()[0]["ruleset_name"] == session.ruleset_name
    session.analyse()
    assert session.result is e and session.stale
    assert session.apply_setting("scale", "1:100") and session.stale
    session.generate()
    assert session.result is not e and not session.stale
    session.load_bytes(MFH.read_bytes(), MFH.name)                     # neue Datei verwirft das Ergebnis ganz
    assert session.result is None and not session.stale


def test_changing_rule_acts_immediately(session):
    session.db.set_action(session.ruleset_name, "IfcWall", "entfernen")
    session.analyse()
    assert not session.df.loc[session.df["ifc_class"].str.startswith("IfcWall"), "is_printed"].all()


def test_metrics_count_only_printed(session):
    k = session.metrics()
    assert k["total"] == int(session.df["is_printed"].sum())
    assert k["total"] + k["nicht_gedruckt"] == len(session.df)
    assert k["druckbar"] + k["kritisch"] + k["nicht_druckbar"] == k["total"]


def test_bulk_action_do_not_print_and_back(session):
    printed = list(session.df.loc[session.df["is_printed"], "guid"][:3])
    session.set_exceptions(printed, "entfernen")
    assert not session.df.set_index("guid").loc[printed, "is_printed"].any()
    assert session.metrics()["nicht_gedruckt"] >= 3
    session.set_exceptions(printed, None)                       # wie Regel
    assert session.df.set_index("guid").loc[printed, "is_printed"].all()


async def test_start_page(user: User):
    await user.open("/")
    for text in ("IFC2Print", "DATEI", "SETUP", "REGELN", "AUSGABE", "PRÜFEN", "IFC-Datei hierher ziehen oder klicken"):
        await user.should_see(text)


async def test_start_model_appears(user: User):
    """Beim Öffnen wird das Beispielmodell geladen und ist voll nutzbar (Modell-Info, STL erzeugen)."""
    await user.open("/")
    await user.should_see("Beispiel: Building-Architecture-IFC2x3.ifc", retries=50)
    await user.should_see("Geschosse · Modell")
    await user.should_see("im Druckbett")
    await user.should_see("STL erzeugen")


def test_without_start_model(monkeypatch, tmp_path):
    from ui import start_model
    import asyncio
    monkeypatch.setenv("IFC2PRINT_STARTMODELL", str(tmp_path / "gibtsnicht.ifc"))
    assert asyncio.run(start_model.fetch()) is None


# --- Analysebericht B-02, B-14, B-20 --------------------------------------------------

def test_generate_only_relevant_setting_without_reanalysis(session):
    """Qualität, Fenster, Türen, Material machen nur das Ergebnis veraltet; Massstab analysiert neu."""
    df = session.df
    session.result = object()
    assert not session.apply_setting("quality", "entwurf")
    assert session.df is df and session.stale and session.quality == "entwurf"
    assert session.apply_setting("scale", "1:100")
    assert session.df is not df


def test_running_generate_is_void_after_change(session, monkeypatch):
    """Ändert der Nutzer während des Laufs etwas, wird das Ergebnis verworfen und nicht im Verlauf eingetragen."""
    from ui import state
    session.quality = "entwurf"
    previous, runs = session.result, len(session.db.export_runs())
    original = state.pipeline.generate

    def generate_with_change(*args, **kwargs):
        result = original(*args, **kwargs)
        session.apply_setting("windows", "ausgeschnitten")              # Klick während des Laufs
        return result
    monkeypatch.setattr(state.pipeline, "generate", generate_with_change)
    assert session.generate() is None
    assert session.result is previous
    assert len(session.db.export_runs()) == runs


def test_classes_without_rule_visible(session):
    """Klassen ohne eigene Regel erscheinen mit der Regel, die stattdessen gilt."""
    entries = {k["ifc_class_name"]: k for k in session.classes_without_rule()}
    assert all(k not in {r["ifc_class_name"] for r in session.rules} for k in entries)
    assert all(k["count"] > 0 for k in entries.values())
    session.db.set_action(session.ruleset_name, "IfcSlab", "entfernen")
    session.analyse()
    assert "IfcSlab" not in {k["ifc_class_name"] for k in session.classes_without_rule()}


def test_notes_of_the_analysis(tmp_path):
    from pathlib import Path
    s = Session(Database(tmp_path / "ui.db"))
    s.load_bytes((Path(__file__).parent.parent / "testdaten" / "MFH_eBKPH_Test.ifc").read_bytes(), "mfh.ifc")
    entries = {p["kind"]: [text for text, _ in p["entries"]] for p in s.check_points}
    assert "IfcFurniture → IfcFurnishingElement" in entries["geerbt"]
    assert entries["keine"]                                     # Klassen ohne Regel, nicht gedruckt


def test_scale_loads_ruleset(session):
    """Massstab = Regelset: Wechsel setzt Öffnungs-Defaults, sperrt Entwurf/Steckverbinder bei 1:500."""
    session.apply_setting("quality", "entwurf")
    session.apply_setting("connectors", True)
    session.apply_setting("windows", "ausgeschnitten")
    session.apply_setting("scale", "1:500")
    assert session.ruleset_name == "1:500"
    assert (session.quality, session.connectors, session.windows) == ("fein", False, "vertieft")
    stairs = session.df[session.df["ifc_class"].isin(["IfcStair", "IfcStairFlight"])]
    assert not stairs["is_printed"].any()                                  # 1:500 ohne Treppen
    session.apply_setting("scale", "1:200")
    assert session.parameter.min_thickness_wall_mm == 1.2 and session.parameter.connectors_allowed


# --- Layout 4c ------------------------------------------------------------------------

def test_status_matrix_sum_equals_metrics(session):
    """Matrix Geschoss × Status: Spaltensummen = Kennzahlen (Totalzeile)."""
    rows, k = session.status_matrix(), session.metrics()
    assert [z["storey"] for z in rows] == session.storeys()
    for status in ("druckbar", "kritisch", "nicht_druckbar", "nicht_gedruckt"):
        assert sum(z[status] for z in rows) == k[status]


async def test_matrix_click_opens_elements(user: User):
    """Klick auf eine Matrix-Spalte → Blatt 03, Tab Bauteile, Filter gesetzt."""
    await user.open("/")
    await user.should_see("Beispiel: Building-Architecture-IFC2x3.ifc", retries=50)
    await user.should_see(marker="matrix-kritisch", retries=50)
    user.find(marker="matrix-kritisch").click()
    await user.should_see("prüfen ×")
    await user.should_see("nur zu druckende")


async def test_matrix_click_shows_only_these_elements(user: User):
    """Klick auf die Matrix zeigt im Viewer nur diese Bauteile; «alle Bauteile zeigen» hebt das auf."""
    def visible_models() -> set[str]:
        scene = next(iter(user.find(kind=ui.scene).elements))
        return {o.id for o in scene.objects.values() if isinstance(o, ui.scene.gltf) and o.visible_}

    await user.open("/")
    await user.should_see(marker="matrix-druckbar", retries=50)
    before = visible_models()
    assert before
    user.find(marker="matrix-druckbar").click()
    await user.should_see(marker="matrix-alle-bauteile", retries=50)
    isolated = visible_models()
    assert isolated and not isolated & before          # nur noch die Auswahl-Ebene
    user.find(marker="matrix-alle-bauteile").click()
    await user.should_not_see(marker="matrix-alle-bauteile")
    assert visible_models() == before


async def test_matrix_click_in_stl_view_switches_to_status(user: User):
    """In der STL-Ansicht (ganze Geschosse) wechselt ein Matrix-Klick auf STAT, sonst sähe man die Auswahl nicht."""
    def active(mode: str) -> bool:
        return "active" in next(iter(user.find(marker=f"ansicht-{mode}").elements)).classes

    await user.open("/")
    await user.should_see(marker="matrix-druckbar", retries=50)
    user.find(marker="ansicht-stl").click()
    assert active("stl")
    user.find(marker="matrix-druckbar").click()
    await user.should_see(marker="matrix-alle-bauteile", retries=50)
    assert active("status") and not active("stl")


def test_scale_suggestion_really_fits(session):
    """Der vorgeschlagene Massstab bringt alle Achsen unter 90 % des Bauraums – und ist der grösste, der das schafft."""
    from config import SCALES
    from core import pipeline
    session.apply_setting("scale", "1:50")
    u = pipeline.model_overview(session.ifc, session.df, 50, session.profile_data, session.angle)
    u["bauraum_mm"] = [m * 0.5 for m in u["model_mm"]]          # Bett künstlich zu klein: Faktor 2 nötig
    name, height = session.scale_suggestion(u)
    denominator = SCALES[name]
    assert all(m * 50 / denominator <= 0.9 * b for m, b in zip(u["model_mm"], u["bauraum_mm"]))
    assert height == u["model_mm"][2] * 50 / denominator
    smaller = [z for z in SCALES.values() if 50 < z < denominator]
    assert all(any(m * 50 / z > 0.9 * b for m, b in zip(u["model_mm"], u["bauraum_mm"])) for z in smaller)


def test_derivation_yields_displayed_number(session):
    """Popup-Rechnung = Kennzahl in der unteren Leiste."""
    from core.output import estimate
    session.quality = "entwurf"
    e = session.generate()
    h = estimate.derivation(e.volume_cm3, e.height_mm, e.layer_height_mm, e.density_g_cm3, e.price_chf_kg)
    assert h["Filament"][0][-1] == f"= {e.grams:.1f} g"
    assert h["Druckzeit"][0][-1] == f"= {e.time_h:.1f} h"
    assert h["Kosten"][0][-1] == f"= CHF {e.cost_chf:.2f}"
    assert (h["Filament"][1], h["Druckzeit"][1], h["Kosten"][1]) == pytest.approx((e.grams, e.time_h, e.cost_chf))


async def test_remove_file_shows_empty_state(user: User):
    """Ohne IFC: Panel und untere Leiste zeigen «Zuerst IFC laden», «Datei entfernen» verschwindet."""
    await user.open("/")
    await user.should_see(marker="matrix-kritisch", retries=50)
    user.find(marker="datei-entfernen").click()
    await user.should_see("Zuerst IFC laden →")
    await user.should_not_see(marker="matrix-kritisch")


def test_session_unload(session):
    session.close_file()
    assert session.ifc is None and session.df is None and session.result is None and session.metrics() == {}


def test_ifc_without_elements_keeps_the_loaded_model(session):
    """Eine Datei ohne Bauteile gibt eine klare Meldung; das bisherige Modell bleibt geladen."""
    import ifcopenshell
    import pytest
    empty = ifcopenshell.file(schema="IFC4")
    empty.createIfcProject(ifcopenshell.guid.new(), Name="leer")
    name, count = session.filename, len(session.df)
    with pytest.raises(ValueError, match="keine Bauteile"):
        session.load_bytes(empty.to_string().encode("utf-8"), "leer.ifc")
    assert session.filename == name and len(session.df) == count


async def test_rule_click_updates_without_error(user: User):
    """Klick auf eine Regel: die Liste wird neu gezeichnet, danach läuft die Analyse-Anzeige ohne Fehler
    (früher brach sie ab, weil der Klick aus der gelöschten Liste heraus JavaScript aufrief)."""
    await user.open("/")
    await user.should_see(marker="matrix-kritisch", retries=50)
    user.find(marker="regel-IfcWall-verdicken").click()
    await asyncio.sleep(3)          # Analyse im Hintergrund; ein Fehler darin lässt den Test beim Abbau scheitern


def test_table_templates_match_the_rows(session):
    """Die Vue-Vorlagen der Bauteiltabelle lesen nur Felder, die table_row liefert, und die Slots
    gehören zu bestehenden Spalten (nach Umbenennungen sonst still leer)."""
    from ui import texts
    from ui.sheet_elements import table_row
    row = table_row(next(session.df.itertuples()))
    for template in (texts.STATUS_SLOT, texts.PRINT_SLOT):
        assert set(re.findall(r"props\.row\.(\w+)", template)) <= set(row)
    source = (Path(__file__).parent.parent / "ui" / "sheet_elements.py").read_text(encoding="utf-8")
    slots = set(re.findall(r'add_slot\("body-cell-(\w+)"', source))
    assert slots <= {c["name"] for c in texts.COLUMNS}
    emitted = set(re.findall(r"\$emit\('(\w+)'", texts.PRINT_SLOT))
    assert emitted <= set(re.findall(r'self\.table\.on\("(\w+)"', source))


def test_button_texts_are_no_identifiers():
    """Knopftexte sind deutsche Wörter, keine Spaltennamen wie «is_printed»."""
    from ui import texts
    for _, text in texts.EXCEPTION_BUTTONS:
        assert "_" not in text
