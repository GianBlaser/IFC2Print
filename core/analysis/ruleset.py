"""Regelwerk: was mit welcher IFC-Klasse passiert.

Aktionen:
  behalten   – Bauteil wird gedruckt, wie es ist
  verdicken  – Bauteil wird gedruckt und bei Bedarf allseitig auf die Mindestwand aufgedickt
  (Wände und Decken in Paketen werden bei beiden Aktionen auf ganze Voxel und die Mindestdicke gebracht,
  siehe core/packages/grouping.py)
  fuellen    – statt der Geometrie wird ein Füllquader gedruckt (Sturz)
  band       – Geländer: als dünne Scheibe vom Boden bis zur Geländerhöhe (core/voxels/band.py)
  entfernen  – Bauteil wird nicht gedruckt

Pro Massstab (1:500, 1:200, 1:100, 1:50) gibt es ein Regelset und die zugehörigen
Parameter (``ScaleParameters``: Mindestdicken, Laibung, Qualitäten, Steckverbinder …).

Ein Regelschlüssel ist die IFC-Klasse («IfcCovering») oder Klasse + PredefinedType
(«IfcCovering.CLADDING»). Der spezifischere Schlüssel gewinnt. Gesucht wird über die
Vererbungskette des Schemas: IfcSlabStandardCase hat keine eigene Regel und erbt die
von IfcSlab. Klassen ohne Regel in der ganzen Kette werden entfernt – in der Praxis
Möbel, Haustechnik und Proxies.

Teile eines Aggregats (Platten und Pfosten eines IfcRoof, Läufe einer IfcStair,
IfcBuildingElementPart einer IfcWall) folgen der Regel ihres Ganzen, sofern es eine hat –
ob ein Dach gedruckt wird, soll nicht davon abhängen, wie das Autorentool es zerlegt.
Feiner steuert ein Schlüssel «Ganzes/Teil» (z.B. «IfcRoof/IfcMember»).
Die Vererbungskette liefert core/ifc/schema.py.

Die Begründung jeder Standardregel und jedes Massstabs steht in der Spalte ``reason`` der Seed-CSVs.
Sie gehört zum Standard und wird nicht in die Datenbank kopiert: Weicht eine Regel vom Standard ab,
heisst es «Eigene Regel» (``rule_reason``).

Eingabe: Regelzeilen (db/seed/regeln.csv oder Datenbank) und die Bauteiltabelle (DataFrame)
Ausgabe: Aktion, Kategorie und wirksamer Regelschlüssel je Bauteil (``Ruleset.classify``)
"""

import csv
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path

import pandas as pd

from core.ifc.schema import class_chain

ACTIONS = ("behalten", "verdicken", "fuellen", "band", "entfernen")
PRINTED_ACTIONS = frozenset({"behalten", "verdicken", "fuellen", "band"})
_SEED = Path(__file__).resolve().parents[2] / "db" / "seed"      # Projektwurzel/db/seed
DEFAULT_CSV = _SEED / "regeln.csv"
SCALE_CSV = _SEED / "massstaebe.csv"
DEFAULT_SCALE = "1:200"
# Regelsets vor der Umstellung auf Massstab-Regelwerke (Okt. 2026)
LEGACY_RULE_SETS = {"Standard 1:200": "1:200", "Volumen 1:500": "1:500"}


@dataclass(frozen=True)
class ScaleParameters:
    """Was neben den Klassenregeln vom Massstab abhängt (Modellmass, mm). Defaults = 1:200.

    Das Druckerprofil bleibt die physikalische Grenze, der Massstab die gestalterische: Decken, Dächer und
    Stützen richten sich nach der Mindestwand des Profils, Wände nach ``min_thickness_wall_mm``.
    """
    ruleset_name: str = DEFAULT_SCALE
    denominator: int = 200
    # Wände (senkrechte Pakete); wirksam max(Profil, dieser Wert). 0.8 mm = 2 Extrusionslinien, 1.2 mm = 3.
    # Dickere Wände behalten ihre skalierte Dicke, gerundet auf ganze Voxel (core/packages/scaling.py).
    min_thickness_wall_mm: float = 1.2
    min_thickness_railing_mm: float | None = 0.8   # Aktion «band»; None = keine Bänder
    reveal_depth_mm: float = 0.4                # Tiefe vertiefter Öffnungen, real rund 8 cm (1:500: ein Voxel)
    min_core_reveal_mm: float = 0.4             # Wandkern, der hinter einer Laibung stehen bleibt
    qualities: tuple[str, ...] = ("fein", "entwurf", "auto")   # wählbare Qualitäten (02 Setup), die übrigen gesperrt
    quality_default: str = "fein"               # Qualität nach dem Wechsel, falls die bisherige nicht erlaubt ist
    connectors_allowed: bool = True             # Steckverbinder zwischen den Geschossteilen möglich
    window_default: str = "vertieft"            # Öffnungsmodus nach dem Wechsel: geschlossen, vertieft, ausgeschnitten
    door_default: str = "vertieft"

    @classmethod
    def from_row(cls, row: dict) -> "ScaleParameters":
        """Aus einer DB- oder CSV-Zeile (Zahlen dürfen als Text kommen, leer = None)."""
        values = {}
        for f in fields(cls):
            w = row.get(f.name)
            if f.name not in row:
                continue
            if f.name == "qualities":
                w = tuple(q.strip() for q in str(w).split(",") if q.strip())
            elif f.name == "connectors_allowed":
                w = bool(int(w))
            elif f.name == "denominator":
                w = int(w)
            elif f.name == "min_thickness_railing_mm":
                w = None if w in (None, "") else float(w)
            elif f.name.endswith("_mm"):
                w = float(w)
            values[f.name] = w
        return cls(**values)

    @staticmethod
    @lru_cache(maxsize=None)
    def default(ruleset_name: str = DEFAULT_SCALE) -> "ScaleParameters":
        """Parameter eines Massstabs direkt aus der Seed-CSV (ohne Datenbank)."""
        ruleset_name = LEGACY_RULE_SETS.get(ruleset_name, ruleset_name)
        with SCALE_CSV.open(encoding="utf-8", newline="") as f:
            for z in csv.DictReader(f):
                if z["ruleset_name"] == ruleset_name:
                    return ScaleParameters.from_row(z)
        raise ValueError(f"Unbekannter Massstab «{ruleset_name}»")


def check_action(action: str) -> str:
    if action not in ACTIONS:
        raise ValueError(f"Unbekannte Aktion «{action}» – erlaubt: {', '.join(ACTIONS)}")
    return action


@lru_cache(maxsize=None)
def _standard_rules(scale: str) -> dict[str, tuple[str, str]]:
    """Standardregeln eines Massstabs aus der Seed-CSV: Regelschlüssel → (Aktion, Begründung)."""
    with DEFAULT_CSV.open(encoding="utf-8", newline="") as f:
        return {z["ifc_class_name"]: (z["action"], z.get("reason") or "")
                for z in csv.DictReader(f) if z["ruleset_name"] == scale}


def rule_reason(scale: str, key: str, action: str) -> str:
    """Begründung der Regel ``key``: die des Standards, solange ``action`` ihm entspricht, sonst «Eigene Regel»."""
    if not key:
        return ""
    standard = _standard_rules(LEGACY_RULE_SETS.get(scale, scale)).get(key)
    if standard is None:
        return "Eigene Regel."
    standard_action, reason = standard
    return reason if action == standard_action else f"Eigene Regel (Standard: {standard_action})."


@lru_cache(maxsize=None)
def scale_reason(scale: str) -> str:
    """Begründung eines Massstabs (Spalte ``reason`` der massstaebe.csv)."""
    with SCALE_CSV.open(encoding="utf-8", newline="") as f:
        return next((z.get("reason") or "" for z in csv.DictReader(f) if z["ruleset_name"] == scale), "")


class Ruleset:
    """Regelwerk eines Massstabs: Regelschlüssel → (Aktion, Kategorie) plus Parameter."""

    def __init__(self, rules: dict[str, str], categories: dict[str, str] | None = None,
                 scale: str = DEFAULT_SCALE, parameter: ScaleParameters | None = None):
        self.rules = {k: check_action(a) for k, a in rules.items()}
        self.categories = categories or {}
        self.scale = LEGACY_RULE_SETS.get(scale, scale)
        self.parameter = parameter or ScaleParameters.default(self.scale)

    @classmethod
    def from_rows(cls, rows: list[dict], scale: str = DEFAULT_SCALE,
                   parameter: ScaleParameters | None = None) -> "Ruleset":
        """Aus Datensätzen mit ifc_class_name, action, category (DB oder CSV)."""
        return cls({z["ifc_class_name"]: z["action"] for z in rows},
                   {z["ifc_class_name"]: z["category"] for z in rows}, scale, parameter)

    @classmethod
    def default(cls, scale: str = DEFAULT_SCALE) -> "Ruleset":
        """Regelwerk direkt aus den Seed-CSVs (ohne Datenbank, z.B. für Skripte und Tests)."""
        scale = LEGACY_RULE_SETS.get(scale, scale)
        with DEFAULT_CSV.open(encoding="utf-8", newline="") as f:
            rows = [z for z in csv.DictReader(f) if z["ruleset_name"] == scale]
        if not rows:
            raise ValueError(f"Unbekannter Massstab «{scale}»")
        return cls.from_rows(rows, scale)

    def rule_source(self, ifc_class: str, predefined_type: str = "", schema: str | None = None, aggregate: str = "") -> str | None:
        """Regelschlüssel, der für das Bauteil gilt, oder None (keine Regel → entfernen).

        Reihenfolge: «Ganzes/Teil» → Regel des Ganzen → Regel des Teils; je über die Vererbungskette.
        """
        part = class_chain(ifc_class, schema)
        if aggregate:
            aggregate_whole = class_chain(aggregate, schema)
            for g in aggregate_whole:
                for k in part:
                    if f"{g}/{k}" in self.rules:
                        return f"{g}/{k}"
            if (key := self._key(aggregate_whole, "")) is not None:
                return key
        return self._key(part, predefined_type)

    def _key(self, chain: tuple[str, ...], predefined_type: str) -> str | None:
        for k in chain:
            if predefined_type and f"{k}.{predefined_type}" in self.rules:
                return f"{k}.{predefined_type}"
            if k in self.rules:
                return k
        return None

    def action(self, ifc_class: str, predefined_type: str = "", schema: str | None = None, aggregate: str = "") -> str:
        return self.rules.get(self.rule_source(ifc_class, predefined_type, schema, aggregate), "entfernen")

    def category(self, ifc_class: str, predefined_type: str = "", schema: str | None = None, aggregate: str = "") -> str:
        return self.categories.get(self.rule_source(ifc_class, predefined_type, schema, aggregate), "Sonstiges")

    def reason(self, key: str) -> str:
        """Begründung der Regel ``key`` (siehe ``rule_reason``)."""
        return rule_reason(self.scale, key, self.rules.get(key, ""))

    def classify(self, df: pd.DataFrame, schema: str | None = None) -> pd.DataFrame:
        """Ergänzt die Bauteiltabelle um action, is_printed, category, rule und reason (gibt eine Kopie zurück).

        ``rule``: der wirksame Regelschlüssel («» = keine Regel, entfernt); ``reason``: seine Begründung. Mit ``schema`` gilt
        die Vererbung; eine Spalte ``aggregate`` (Klasse des Aggregats) aktiviert die Aggregat-Regel.
        """
        df = df.copy()
        empty = pd.Series("", index=df.index)
        rows = zip(df["ifc_class"], df["predefined_type"] if "predefined_type" in df else empty, df["aggregate"] if "aggregate" in df else empty)
        rule = [self.rule_source(k, t, schema, g) for k, t, g in rows]
        df["action"] = [self.rules.get(r, "entfernen") for r in rule]
        df["category"] = [self.categories.get(r, "Sonstiges") for r in rule]
        df["rule"] = [r or "" for r in rule]
        df["reason"] = df["rule"].map({r: self.reason(r) for r in set(df["rule"])})
        df["is_printed"] = df["action"].isin(PRINTED_ACTIONS)
        return df
