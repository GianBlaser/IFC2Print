"""Verarbeitung: vom IFC zur druckbaren STL, ohne Oberfläche.

Eingabe: IFC-Datei, Regeln und Einstellungen (über core/pipeline.py)
Ausgabe: Bauteiltabelle, Prüfpunkte und Result mit Teilen und Downloads

Ablauf: core/pipeline.py (Fassade für Oberfläche, Skripte und Tests) → core/generation.py (Erzeugung).
Die Unterordner folgen den Schritten: ifc → analysis → packages → voxels → openings → parts → connectors → output.
"""
