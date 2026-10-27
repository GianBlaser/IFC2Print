"""Sitzungszustand eines Browser-Tabs – Bindeglied zwischen Oberfläche und core.pipeline.

Zweck:   Hält zu den Einstellungen (ui/settings.py) das geladene Modell, die Bauteiltabelle, das Ergebnis und die
         Ausnahmen je Bauteil und führt die Abläufe aus: Datei laden, analysieren, Einstellung ändern, erzeugen.
         Jede Einstellungsänderung markiert ein vorhandenes Ergebnis als veraltet: Es bleibt sichtbar, aber die
         Downloads sind gesperrt, bis neu erzeugt ist – so wird nie mit veralteten Daten exportiert. Eine neue Datei
         verwirft das Ergebnis ganz. Neu analysiert wird nur, wenn die Änderung die Analyse betrifft
         (ANALYSIS_FIELDS); Qualität, Fenster, Türen und Material wirken erst beim Erzeugen.
         Zahlen und Listen für die Blätter rechnet ui/state_views.py, den Verlaufseintrag baut ui/run_history.py.
Eingabe: die Datenbank (db.database.Database); IFC-Bytes oder ein geöffnetes IfcModel; Einstellungen als Attribute
Ausgabe: Session mit Modell, Tabelle (df), Ergebnis, Kennzahlen, Vorschau-GLBs und Downloads für die Blätter
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core import pipeline
from core.analysis.ruleset import Ruleset
from core.ifc.model import IfcModel
from ui import run_history, state_views
from ui.settings import ANALYSIS_FIELDS, Settings


@dataclass
class Session(Settings):
    ifc: IfcModel | None = None
    filename: str = ""
    df: pd.DataFrame | None = None
    angle: float = 0.0                       # erkannte Ausrichtung (0, wenn ausgeschaltet)
    result: pipeline.Result | None = None
    progress: tuple[str, float] = ("", 0.0)
    stale: bool = False                    # Ergebnis passt nicht mehr zu den Einstellungen
    running: bool = False                      # eine Erzeugung läuft – weitere Klicks werden ignoriert
    exceptions: dict[str, str] = field(default_factory=dict)   # GUID → Aktion (übersteuert Regel/Umgebung)
    check_points: list[dict] = field(default_factory=list)   # Prüfpunkte der Analyse (Blatt 05 Prüfen, PDF)
    _revision: int = 0                            # zählt jede Änderung – ein laufendes Erzeugen gilt nur ohne Änderung
    _boxes: tuple | None = None                # ((Massstab, Winkel), Boxen) – Cache fürs Anklicken

    # --- Auswertungen (Rechnung in ui/state_views.py) ---------------------------

    def metrics(self) -> dict[str, int]:
        """Kennzahlen: gedruckte Bauteile gesamt, nicht gedruckte und je Druckbarkeitsstatus."""
        return state_views.metrics(self.df)

    def status_matrix(self) -> list[dict]:
        """Je Geschoss (Reihenfolge wie storeys()): Anzahl ok / kritisch / nicht druckbar / nicht gedruckt."""
        return state_views.status_matrix(self.ifc, self.df)

    def classes_without_rule(self, storey: str | None = None) -> list[dict]:
        """Klassen des Modells ohne eigene Regel im Regelset: [{ifc_class_name, rule, action, category, count}].

        ``storey``: nur die Bauteile dieses Geschosses (Geschoss-Auswahl in der Matrix)."""
        df = self.df if storey is None or self.df is None else self.df[self.df["storey"] == storey]
        return state_views.classes_without_rule(df, self.rules)

    def scale_suggestion(self, overview: dict, margin: float = 0.9) -> tuple[str, float] | None:
        """Kleinster Massstab-Sprung, bei dem alle Achsen ≤ ``margin`` des Bauraums liegen: (Name, Höhe mm)."""
        return state_views.scale_suggestion(overview, self.scale_denominator, margin)

    def report_context(self) -> dict:
        """Was der PDF-Report aus der Sitzung braucht: IFC-Kopfdaten, Abmessungen und Einstellungen."""
        return pipeline.report_context(self.ifc, self.df, self.filename, scale=self.scale_denominator,
                                       ruleset_name=self.ruleset_name, profile=self.profile_data,
                                       material=self.material_data, angle=self.angle, windows=self.windows,
                                       doors=self.doors)

    def check_report_pdf(self) -> bytes:
        """Prüfbericht ohne Ergebnis: derselbe Report, Seite 1 ohne Urteil und Druckteile."""
        return state_views.check_report_pdf(self.df, self.report_context(), self.check_points)

    def report_pdf(self) -> bytes:
        """PDF-Report zum Ergebnis (Übergabeblatt)."""
        return self.result.report_pdf(self.df, self.report_context())

    # --- Abläufe --------------------------------------------------------------

    def load_bytes(self, data: bytes, filename: str) -> None:
        self.load_model(IfcModel.from_bytes(data), filename)

    def load_model(self, ifc: IfcModel, filename: str) -> None:
        """Bereits geöffnetes Modell übernehmen (z.B. das geteilte Startmodell).

        Scheitert die Analyse, bleibt das bisherige Modell geladen und der Fehler geht an die Oberfläche.
        """
        if ifc.building_elements.empty:
            raise ValueError("Das IFC enthält keine Bauteile mit Geometrie.")
        field_names = ("ifc", "filename", "exceptions", "selected_storeys", "result", "stale", "df",
                       "check_points", "angle")
        previous = {name: getattr(self, name) for name in field_names}
        self.ifc = ifc
        self.filename = filename
        self.exceptions = {}
        self.selected_storeys = None
        self.result, self.stale = None, False
        try:
            self.analyse()
        except Exception:
            for name, value in previous.items():
                setattr(self, name, value)
            raise

    def close_file(self) -> None:
        """Datei schliessen: zurück zum leeren Startzustand (Einstellungen bleiben)."""
        self.ifc, self.df, self.filename = None, None, ""
        self.result, self.stale = None, False
        self.exceptions, self.selected_storeys = {}, None
        self.check_points, self.angle = [], 0.0
        self._boxes = None
        self._revision += 1

    def analyse(self) -> None:
        self.stale = self.result is not None
        self._revision += 1
        if self.ifc is not None:
            ruleset = Ruleset.from_rows(self.rules, self.scale, self.parameter)
            self.df = pipeline.analyse(self.ifc, ruleset, self.scale_denominator, self.profile_data,
                                       self.exceptions, self.selected_storeys)
            self.angle = pipeline.alignment_angle(self.ifc, self.df) if self.align else 0.0
            self.check_points = pipeline.check_points(self.ifc, self.df, ruleset.rules)

    def apply_setting(self, field_name: str, value) -> bool:
        """Setzt eine Einstellung und markiert das Ergebnis als veraltet; True, wenn neu analysiert wurde.

        Ein neuer Massstab lädt sein Regelwerk (siehe Settings.apply_scale_defaults).
        """
        setattr(self, field_name, value)
        if field_name == "scale":
            self.apply_scale_defaults()
        self.stale = self.result is not None
        self._revision += 1
        if field_name in ANALYSIS_FIELDS:
            self.analyse()
            return True
        return False

    def set_exceptions(self, guids: Iterable[str], action: str | None) -> None:
        """Mehrere Bauteile drucken / nicht drucken (None = wie Regel) und neu analysieren."""
        for guid in guids:
            if action is None:
                self.exceptions.pop(guid, None)
            else:
                self.exceptions[guid] = action
        self.analyse()

    def generate(self) -> pipeline.Result | None:
        """Läuft im Hintergrund-Thread; meldet den Fortschritt über self.progress.

        Rückgabe: das Ergebnis, oder None, wenn der Nutzer während des Laufs etwas geändert hat.
        Dann passt das Ergebnis nicht mehr zu den Einstellungen und wird verworfen (kein Verlaufseintrag).
        """
        # Momentaufnahme: ändert der Nutzer währenddessen etwas, gilt das Ergebnis nicht
        df, revision = self.df, self._revision
        run = run_history.settings_of_run(self, self.filename)

        def set_progress(phase: str, fraction: float) -> None:
            self.progress = (phase, fraction)

        pitch, note = pipeline.resolve_quality(self.quality, self.ifc, df, self.scale_denominator, self.angle)
        result = pipeline.generate(
            self.ifc, df, scale=self.scale_denominator, pitch_mm=pitch,
            profile=self.profile_data, material=self.material_data, angle=self.angle,
            windows=self.windows, doors=self.doors, connectors=self.connectors,
            exceptions=dict(self.exceptions), progress=set_progress, parameter=self.parameter)
        if self._revision != revision:
            return None
        if note:
            result.warnings.insert(0, note)
        self.db.write_export_run({**run, **run_history.figures_of_run(result, df)})
        self.result, self.stale = result, False
        return result

    # --- Modell, Vorschau und Downloads ---------------------------------------

    def project_name(self) -> str:
        """Name des IfcProject («» ohne Modell oder ohne Namen) – für die Modellkarte in Blatt 01."""
        projects = self.ifc.model.by_type("IfcProject") if self.ifc is not None else []
        return (projects[0].Name or "") if projects else ""

    def storeys(self) -> list[str]:
        return pipeline.storey_order(self.ifc, self.df)

    def csv(self) -> bytes:
        return pipeline.elements_csv(self.df)

    def preview(self) -> tuple[dict, dict[str, bytes], dict]:
        """(IFC-GLB je Geschoss, Status-GLB je Geschoss, Modell-Übersicht)."""
        m = self.scale_denominator
        return (pipeline.ifc_preview(self.ifc, self.df, m, self.angle),
                pipeline.status_preview(self.ifc, self.df, m, self.angle),
                pipeline.model_overview(self.ifc, self.df, m, self.profile_data, self.angle))

    def selection_preview(self, guids: Iterable[str]) -> dict[str, bytes]:
        return pipeline.selection_preview(self.ifc, self.df, guids, self.scale_denominator, self.angle)

    def element_box(self, guid: str) -> tuple | None:
        """(min, max) des Bauteils im Modellmass nach der Ausrichtung – für die Kamera."""
        key = (self.scale_denominator, self.angle)
        if self._boxes is None or self._boxes[0] != key:
            self._boxes = (key, pipeline.element_boxes(self.ifc, *key))
        return self._boxes[1].get(guid)

    def element_at_point(self, storey: str, point, printed_only: bool = True) -> str | None:
        self.element_box("")                          # Boxen-Cache für Massstab und Winkel aufbauen
        return pipeline.element_at_point(self._boxes[1], self.df, storey, point, printed_only=printed_only)

    def package_min_thickness(self, guid: str) -> float:
        """Mindestdicke, auf die das Paket eines Bauteils gebracht wird (wie core.pipeline.generate)."""
        return pipeline.package_min_thickness(self.ifc, guid, self.profile_data["min_wall_mm"],
                                              self.parameter.min_thickness_wall_mm)

    def frame(self) -> tuple[np.ndarray, float, float]:
        """(Mitte unten, grösste Ausdehnung, Höhe) im Modellmass [mm]."""
        return pipeline.frame(self.ifc, self.scale_denominator, self.angle)
