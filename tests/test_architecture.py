"""Struktur-Regeln: Verarbeitung (core/) und Darstellung (ui/) bleiben getrennt."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def _imports(folder: str) -> set[str]:
    names = set()
    for file in (PROJECT_ROOT / folder).rglob("*.py"):      # mit Unterordnern (core/ifc/ …)
        for nodes in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(nodes, ast.Import):
                names |= {a.name.split(".")[0] for a in nodes.names}
            elif isinstance(nodes, ast.ImportFrom) and nodes.module:
                names.add(nodes.module.split(".")[0])
    return names


def test_core_knows_no_user_interface():
    assert not {"nicegui", "ui", "fastapi", "app"} & _imports("core")


def test_db_knows_no_user_interface():
    assert not {"nicegui", "ui", "app"} & _imports("db")


def test_no_javascript_in_project():
    """Vorgabe Leistungsnachweis: ausschliesslich Python (keine .js-Dateien)."""
    js = [p for p in PROJECT_ROOT.rglob("*.js") if ".venv" not in p.parts]
    assert not js
