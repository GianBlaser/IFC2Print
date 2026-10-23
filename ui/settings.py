"""Einstellungen einer Sitzung: was der Nutzer wählt und was daraus folgt.

Zweck:   Hält die Wahl des Nutzers (Druckerprofil, Material, Massstab, Qualität, Fenster, Türen …) und leitet daraus ab,
         was dazu gehört: Massstabszahl, Regeln, Parameter des Regelsets, Profil- und Materialdaten. Ein neuer Massstab
         setzt seine Standardwerte (apply_scale_defaults). Die Sitzung (ui/state.py) baut darauf auf und ergänzt
         Modell, Ergebnis und Abläufe.
Eingabe: die Datenbank (db.database.Database) mit Druckerprofilen, Material, Regeln und Massstabsparametern
Ausgabe: die Klasse Settings; Session in ui/state.py erweitert sie
"""

from dataclasses import dataclass, field

from config import OUTPUT_TARGET_DEFAULT, OUTPUT_TARGETS, QUALITY_DEFAULT, SCALE_DEFAULT, SCALES, OutputTarget
from core.analysis.ruleset import ScaleParameters
from db.database import Database

# Einstellungen, die Regeln, Dicken oder Ausrichtung der Analyse verändern
ANALYSIS_FIELDS = frozenset({"profile", "scale", "align", "selected_storeys"})


@dataclass
class Settings:
    db: Database
    profile: str = ""
    material: str = ""
    scale: str = SCALE_DEFAULT
    quality: str = QUALITY_DEFAULT
    align: bool = True
    windows: str = ScaleParameters.window_default
    doors: str = ScaleParameters.door_default
    selected_storeys: list[str] | None = None   # nur diese Geschosse drucken (None = alle)
    connectors: bool = False                   # Steckverbinder: wirkt erst beim Erzeugen (nicht in ANALYSIS_FIELDS)
    theme: str = "light"
    target: str = OUTPUT_TARGET_DEFAULT           # Ausgabeziel (config.OUTPUT_TARGETS); umgesetzt ist nur FDM

    _printer_profiles: dict = field(default_factory=dict)
    _materials: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._printer_profiles = {p["name"]: p for p in self.db.profiles()}
        self._materials = {m["name"]: m for m in self.db.materials()}
        self.profile = self.profile or next(iter(self._printer_profiles))
        self.material = self.material or next(iter(self._materials))

    # --- abgeleitete Werte --------------------------------------------------

    @property
    def scale_denominator(self) -> int:
        return SCALES[self.scale]

    @property
    def output_target(self) -> OutputTarget:
        return next(z for z in OUTPUT_TARGETS if z.key == self.target)

    @property
    def ruleset_name(self) -> str:
        """Regeln und Parameter gehören zum Massstab (ein Regelset je Stufe)."""
        return self.scale

    @property
    def parameter(self) -> ScaleParameters:
        return ScaleParameters.from_row(self.db.scale_parameters(self.scale))

    @property
    def profile_data(self) -> dict:
        return self._printer_profiles[self.profile]

    @property
    def material_data(self) -> dict:
        return self._materials[self.material]

    @property
    def rules(self) -> list[dict]:
        return self.db.rules(self.ruleset_name)

    def apply_scale_defaults(self) -> None:
        """Ein neuer Massstab lädt sein Regelwerk: Öffnungen auf die Defaults, nicht erlaubte
        Qualität auf den Default, Steckverbinder aus, wenn sie bei diesem Massstab nicht gehen."""
        p = self.parameter
        self.windows, self.doors = p.window_default, p.door_default
        if self.quality not in p.qualities:
            self.quality = p.quality_default
        if not p.connectors_allowed:
            self.connectors = False
