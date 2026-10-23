"""Beispielmodell, das beim Öffnen der Seite erscheint.

Zweck:   Das Beispiel wird einmal je Serverprozess geöffnet und vorberechnet (Triangulierung, Bauteiltabelle,
         Öffnungen) und von allen Browser-Tabs gemeinsam genutzt – das IfcModel wird danach nur noch gelesen.
         Fehlt die Datei, startet die App einfach ohne Beispiel.
Eingabe: Pfad aus config.START_MODEL, überschreibbar mit der Umgebungsvariable IFC2PRINT_STARTMODELL (Tests)
Ausgabe: fetch() liefert das geöffnete IfcModel oder None, wenn die Datei fehlt oder defekt ist
"""

import asyncio
import logging
import os
from pathlib import Path

from nicegui import run

from config import START_MODEL
from core.ifc.model import IfcModel

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_loaded: dict[Path, IfcModel] = {}                          # fertig geladene Modelle je Pfad
_loading: dict[Path, tuple[asyncio.AbstractEventLoop, asyncio.Future]] = {}


def file_path() -> Path:
    """Pfad aus der Umgebungsvariable IFC2PRINT_STARTMODELL (Tests) oder config.START_MODEL."""
    p = Path(os.environ.get("IFC2PRINT_STARTMODELL", START_MODEL))
    return p if p.is_absolute() else _PROJECT_ROOT / p


def _open(p: Path) -> IfcModel:
    ifc = IfcModel.open_file(p)
    ifc.geometry, ifc.building_elements, ifc.plates, ifc.filler   # einmal berechnen, danach nur noch lesen
    return ifc


async def fetch() -> IfcModel | None:
    """Das geteilte Startmodell (beim ersten Aufruf laden, danach sofort).

    Gleichzeitige Aufrufe warten auf denselben Ladevorgang (pro Event-Loop).
    """
    p = file_path()
    if p in _loaded:
        return _loaded[p]
    if not p.exists():
        logging.info("Kein Startmodell: %s nicht gefunden", p)
        return None
    loop = asyncio.get_running_loop()
    if p not in _loading or _loading[p][0] is not loop:
        _loading[p] = (loop, asyncio.ensure_future(run.io_bound(_open, p)))
    try:
        _loaded[p] = await asyncio.shield(_loading[p][1])
        return _loaded[p]
    except Exception:                                   # defekte Datei: App läuft ohne Beispiel weiter
        logging.exception("Startmodell %s konnte nicht geladen werden", p)
        return None
