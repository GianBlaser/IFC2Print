"""Tests der Kommandozeilen-Skripte: Der Schnellstart-Befehl aus dem README muss laufen."""

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / "scripts" / f"{name}.py")
    loaded_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded_module)
    return loaded_module


def test_generate_stl_as_in_readme(tmp_path, monkeypatch):
    """README-Schnellstart: Regeln kommen aus dem gewählten Massstab, es entstehen ZIP und PDF."""
    monkeypatch.setenv("IFC2PRINT_DB", str(tmp_path / "regeln.db"))
    output = tmp_path / "output"
    _script("generate_stl").main([str(PROJECT_ROOT / "testdaten" / "MFH_eBKPH_Test.ifc"), "--scale", "1:200",
                                  "--quality", "entwurf", "--output", str(output)])
    assert (output / "MFH_eBKPH_Test_geschosse.zip").stat().st_size > 0
    assert (output / "MFH_eBKPH_Test_report.pdf").read_bytes().startswith(b"%PDF")
