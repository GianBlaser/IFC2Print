"""Tests der Dokumentation: README und docs/ dürfen nichts nennen, was es im Code nicht (mehr) gibt.

Geprüft werden Inline-Code (`…`) und Links: Pfade und Dateien müssen existieren, Namen im Quelltext vorkommen,
und «`KONSTANTE` = Wert» muss config.py entsprechen. docs/REFERENZ.md muss dem Stand von scripts/reference.py
entsprechen.
"""

import importlib.util
import re
from pathlib import Path

import pytest

import config
from core.ifc.schema import schema_wrapper

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = [PROJECT_ROOT / "README.md", *sorted((PROJECT_ROOT / "docs").glob("*.md"))]
SOURCE_SUFFIXES = {".py", ".sql", ".csv", ".toml", ".j2", ".css", ".js"}
SKIPPED_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache"}
FILE_SUFFIX = re.compile(r"\.(py|csv|sql|md|json|css|j2|html|toml|txt|ifc|svg|db|png)$")
IDENTIFIER = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*(\(\))?$")
IFC_KEY = re.compile(r"^Ifc\w+(\.\w+)?(/Ifc\w+)?$")          # Regelschlüssel: Klasse, Klasse.TYP, Ganzes/Teil
GENERATED_FILES = {".nicegui/secret.txt"}                      # entsteht erst beim Start der App
EXTERNAL_NAMES = {"WEASYPRINT_DLL_DIRECTORIES"}               # Umgebungsvariable von WeasyPrint, nicht im Code
UNITS = {"m": 1000.0, "%": 0.01}                              # «`JOINT_WIDTH_MM` = 2 m», «`ISLAND_RATIO` = 25 %»


def _project_files() -> list[Path]:
    """Alle Dateien des Projekts samt Testdaten, ohne Umgebung, Caches und erzeugte Dateien (output/)."""
    return [p for p in PROJECT_ROOT.rglob("*") if p.is_file() and not SKIPPED_DIRS & set(parts := p.relative_to(PROJECT_ROOT).parts)
            and parts[0] != "output"]


def _in_ifc_schema(name: str) -> bool:
    """IFC-Name (Klasse, Beziehung, Materialdefinition) in einem der Schemas."""
    for schema in ("IFC2X3", "IFC4", "IFC4X3_ADD2"):
        try:
            schema_wrapper.schema_by_name(schema).declaration_by_name(name)
            return True
        except (RuntimeError, ValueError, KeyError):
            continue
    return False


@pytest.fixture(scope="module")
def source_words() -> set[str]:
    """Alle Wörter des Quelltexts (Namen, Spalten, Regelschlüssel)."""
    words = set()
    for p in _project_files():
        if p.suffix in SOURCE_SUFFIXES:
            words |= set(re.findall(r"\w+", p.read_text(encoding="utf-8", errors="ignore")))
    return words


def _inline_code(document: Path) -> list[str]:
    """Inline-Code des Dokuments, ohne Codeblöcke (```), Tabellenmaskierung «\\|» aufgelöst."""
    text = re.sub(r"```.*?```", "", document.read_text(encoding="utf-8"), flags=re.S)
    return [c.strip().replace("\\|", "|") for c in re.findall(r"`([^`\n]+)`", text)]


def _links(document: Path) -> list[str]:
    """Relative Linkziele des Dokuments (ohne Webadressen und Anker)."""
    targets = re.findall(r"\]\(([^)\s]+)\)", document.read_text(encoding="utf-8"))
    return [t.split("#")[0] for t in targets if not t.startswith(("http", "#", "mailto:"))]


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda p: p.name)
def test_links_exist(document):
    missing = [t for t in _links(document) if not (document.parent / t).exists()]
    assert not missing, f"{document.name}: Links ohne Ziel: {missing}"


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda p: p.name)
def test_paths_and_files_exist(document):
    """`core/analysis/ruleset.py` muss existieren; `ruleset.py` (ohne Ordner) irgendwo im Projekt."""
    files = _project_files()
    relative = [p.relative_to(PROJECT_ROOT) for p in files]
    paths = {p.as_posix() for p in relative} | {d.as_posix() for p in relative for d in p.parents if d.parts}
    names = {p.name for p in files}
    missing = []
    for code in (c.strip('"') for c in _inline_code(document)):
        if code in GENERATED_FILES:
            continue
        if " " in code or "{" in code or code.startswith("/") or IFC_KEY.match(code)                 or not (FILE_SUFFIX.search(code) or "/" in code):
            continue
        if "/" in code:     # vom Projektordner aus oder als Ende eines Pfads («templates/report.html.j2»)
            path = code.split("(")[0].rstrip("/")
            stem = path if FILE_SUFFIX.search(path) else path.rsplit(".", 1)[0]
            if not any(p == c or p.endswith("/" + c) for p in paths for c in (path, stem, stem + ".py")):
                missing.append(code)
        elif code not in names:
            missing.append(code)
    assert not missing, f"{document.name}: Pfade/Dateien ohne Gegenstück: {missing}"


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda p: p.name)
def test_names_exist_in_source(document, source_words):
    """`Ruleset.classify`, `ScaleParameters`, `min_thickness_wall_mm`: jeder Teil kommt im Quelltext vor.
    IFC-Namen (`IfcBuiltElement`, `IfcRoof/IfcMember`) dürfen stattdessen in einem der IFC-Schemas stehen."""
    def known(code: str) -> bool:
        if code in EXTERNAL_NAMES or all(part in source_words for part in code.removesuffix("()").split(".")):
            return True
        return bool(IFC_KEY.match(code)) and all(_in_ifc_schema(k.split(".")[0]) for k in code.split("/"))

    missing = [code for code in _inline_code(document)
               if IDENTIFIER.match(code) and not FILE_SUFFIX.search(code) and not known(code)]
    assert not missing, f"{document.name}: Namen ohne Gegenstück im Code: {missing}"


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda p: p.name)
def test_values_match_config(document):
    """«`MIN_WALL_MM` = 0.8 mm» im Text muss dem Wert in config.py entsprechen (Meter und Prozent umgerechnet)."""
    text = document.read_text(encoding="utf-8")
    wrong = [(name, f"{value} {unit}".strip(), getattr(config, name, None))
             for name, value, unit in re.findall(r"`([A-Z][A-Z0-9_]+)` = (\d+(?:\.\d+)?) ?(m\b|%)?", text)
             if getattr(config, name, None) is None
             or abs(float(getattr(config, name)) - float(value) * UNITS.get(unit, 1.0)) > 1e-9]
    assert not wrong, f"{document.name}: Werte weichen von config.py ab: {wrong}"


def test_reference_is_current():
    spec = importlib.util.spec_from_file_location("reference", PROJECT_ROOT / "scripts" / "reference.py")
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    assert reference.TARGET.read_text(encoding="utf-8") == reference.render(), \
        "docs/REFERENZ.md ist veraltet: python scripts/reference.py ausführen"
