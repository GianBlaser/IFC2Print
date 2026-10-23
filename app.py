"""IFC2Print – Massstabsmodell-Generator: registriert die Webseite und startet NiceGUI.

Zweck:   verbindet Datenbank, Sitzungszustand (ui/state.py) und Seite (ui/page.py) zu einer Web-App.
Eingabe: Umgebungsvariablen IFC2PRINT_DB, IFC2PRINT_HOST, IFC2PRINT_SECRET (alle optional)
Ausgabe: Weboberfläche unter http://127.0.0.1:8080 (Start über python main.py)
"""

import os
import secrets
from pathlib import Path

from nicegui import app, background_tasks, ui

from db.database import DEFAULT_PATH, Database
from ui import start_model
from ui.page import Page
from ui.state import Session

db = Database(os.environ.get("IFC2PRINT_DB", DEFAULT_PATH))   # Tests setzen eine Temp-DB


app.on_startup(lambda: background_tasks.create(start_model.fetch()))   # Beispiel früh vorbereiten


@ui.page("/")
def start_page() -> None:
    page = Page(Session(db, theme=app.storage.user.get("theme", "light")))
    ui.context.client.on_delete(page.viewer.release)   # GLB-Zwischenspeicher der Sitzung freigeben
    ui.timer(0.1, page.load_start_model, once=True)


def storage_key() -> str:
    """Schlüssel, mit dem NiceGUI die Browser-Speicherung signiert (Theme, Ansicht).

    Aus der Umgebungsvariable IFC2PRINT_SECRET, sonst beim ersten Start zufällig erzeugt und in
    .nicegui/secret.txt gemerkt (nicht im Repo, siehe .gitignore).
    """
    from_surroundings = os.environ.get("IFC2PRINT_SECRET")
    if from_surroundings:
        return from_surroundings
    file = Path(__file__).resolve().parent / ".nicegui" / "secret.txt"
    if not file.exists():
        file.parent.mkdir(exist_ok=True)
        file.write_text(secrets.token_hex(16), encoding="utf-8")
    return file.read_text(encoding="utf-8").strip()


def launch() -> None:
    """Startet den Webserver. Nur auf diesem Rechner erreichbar, ausser IFC2PRINT_HOST sagt etwas anderes."""
    ui.run(title="IFC2Print", favicon="assets/favicon.svg", storage_secret=storage_key(),
           host=os.environ.get("IFC2PRINT_HOST", "127.0.0.1"), port=8080, reload=False, show=False,
           reconnect_timeout=60.0)   # Tab-Wechsel (Browser drosselt WebSocket) nicht sofort als "Connection lost" werten


if __name__ in {"__main__", "__mp_main__"}:
    launch()
