"""Gemeinsame Test-Einstellungen: Temp-Datenbank für die App, NiceGUI-Testplugin."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("IFC2PRINT_DB", str(Path(tempfile.mkdtemp()) / "test.db"))
# Kleines Startmodell, damit der Oberflächentest schnell bleibt
os.environ.setdefault("IFC2PRINT_STARTMODELL", str(Path(__file__).parent.parent / "testdaten" / "Building-Architecture-IFC2x3.ifc"))

pytest_plugins = ["nicegui.testing.user_plugin"]
