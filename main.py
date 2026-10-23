"""IFC2Print – Start des Programms.

Zweck:   Startet die Weboberfläche, mit der aus einem IFC-Modell druckbare STL-Dateien werden.
Eingabe: keine; optional die Umgebungsvariablen IFC2PRINT_DB (Pfad der Datenbank),
         IFC2PRINT_HOST (Adresse, Standard 127.0.0.1) und IFC2PRINT_SECRET (Schlüssel der Browser-Speicherung).
Ausgabe: Weboberfläche unter http://127.0.0.1:8080

main.py startet nur. Die Seite wird in app.py registriert, die Oberfläche steht in ui/,
die Fachlogik in core/ und die Daten in db/.
"""

import app

if __name__ in {"__main__", "__mp_main__"}:
    app.launch()
