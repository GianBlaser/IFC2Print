"""Gemeinsame Test-Einstellungen: Temp-Datenbank für die App, NiceGUI-Testplugin, Kontext des PDF-Reports."""

import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("IFC2PRINT_DB", str(Path(tempfile.mkdtemp()) / "test.db"))
# Kleines Startmodell, damit der Oberflächentest schnell bleibt
os.environ.setdefault("IFC2PRINT_STARTMODELL", str(Path(__file__).parent.parent / "testdaten" / "Building-Architecture-IFC2x3.ifc"))

pytest_plugins = ["nicegui.testing.user_plugin"]


@pytest.fixture
def report_context() -> dict:
    """Kontext des PDF-Reports ohne IFC-Modell (wie core.output.report_data.report_context)."""
    meta = {"projekt": "Testprojekt", "datei": "test.ifc", "schema": "IFC4", "storeys": ["UG", "EG", "OG"],
            "real_m": [12.0, 8.5, 6.2], "model_mm": [60.0, 42.5, 31.0], "bauraum_mm": [250.0, 210.0, 220.0],
            "fits": True, "recommendation": None}
    return {"ifc_meta": meta, "scale": 200, "ruleset_name": "1:200", "material": {"name": "PETG"},
            "profile": {"name": "Prusa MK4", "nozzle_mm": 0.4, "min_wall_mm": 0.8},
            "angle": -12.5, "windows": "vertieft", "doors": "geschlossen"}
