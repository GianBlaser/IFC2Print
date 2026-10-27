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

Bedingungen: An jeden Schlüssel kann in eckigen Klammern eine Bedingung aus ``CONDITIONS`` angehängt werden,
z.B. «IfcCovering[aussen]» oder «IfcMember[duenner_als:0.8]». Sie gilt nur für Bauteile, die sie erfüllen;
die übrigen fallen auf den Schlüssel ohne Bedingung zurück. Je Stufe der Vererbungskette gilt:
Klasse.TYP[Bedingung] → Klasse.TYP → Klasse[Bedingung] → Klasse. Treffen mehrere Bedingungen zu, gewinnt die
erste in ``CONDITIONS`` (bei «duenner_als» der kleinere Grenzwert). Fehlt die Eigenschaft im IFC
(kein IsExternal), trifft weder «aussen» noch «innen» zu.

Die Standardregeln stehen in db/seed/regeln.csv: eine Zeile gilt für die Massstäbe der Spalte ``scales``
(«alle» oder eine Liste «1:500,1:200»). Gibt es für einen Schlüssel mehrere Zeilen, gewinnt die mit den wenigsten
Massstäben – so steht der Normalfall einmal da und jeder Massstab nur mit seinen Abweichungen (``seed_rules``).

Die Begründung jeder Standardregel und jedes Massstabs steht in der Spalte ``reason`` der Seed-CSVs.
Sie gehört zum Standard und wird nicht in die Datenbank kopiert: Weicht eine Regel vom Standard ab,
heisst es «Eigene Regel» (``rule_reason``).

Eingabe: Regelzeilen (``seed_rules`` aus db/seed/regeln.csv oder Datenbank) und die Bauteiltabelle (DataFrame)
Ausgabe: Aktion, Kategorie und wirksamer Regelschlüssel je Bauteil (``Ruleset.classify``)
"""

import csv
import math
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path

import pandas as pd

from config import SCALES
from core.ifc.schema import class_chain

ACTIONS = ("behalten", "verdicken", "fuellen", "band", "entfernen")
PRINTED_ACTIONS = frozenset({"behalten", "verdicken", "fuellen", "band"})
_SEED = Path(__file__).resolve().parents[2] / "db" / "seed"      # Projektwurzel/db/seed
DEFAULT_CSV = _SEED / "regeln.csv"
SCALE_CSV = _SEED / "massstaebe.csv"
DEFAULT_SCALE = "1:200"
ALL_SCALES = "alle"                         # Spalte «scales» der regeln.csv: Zeile gilt für jeden Massstab
# Massstab-Parameter, die in Blatt 03 (Tab «Massstab») einstellbar sind → (Beschriftung, kleinster, grösster Wert [mm]).
# Der Standard bleibt massstaebe.csv; eigene Werte speichert die Datenbank je Massstab (Tabelle scale_override).
EDITABLE_PARAMETERS = {
    "min_thickness_wall_mm": ("Mindestdicke Wände", 0.4, 5.0),
    "min_thickness_railing_mm": ("Dicke Geländer-Band", 0.4, 5.0),
    "reveal_depth_mm": ("Laibungstiefe", 0.2, 0.35),
    "min_core_reveal_mm": ("Kern hinter der Laibung", 0.4, 5.0),
}
# Bedingungen eines Schlüssels «Klasse[Bedingung]», in der Reihenfolge ihres Vorrangs → Beschriftung.
# aussen/innen: IsExternal, tragend: LoadBearing (Pset_…Common), duenner_als:<mm>: kleinste Dicke am Modell [mm]
CONDITIONS = {"duenner_als": "dünner als {} mm", "tragend": "tragend", "aussen": "aussen", "innen": "innen"}
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
    # Grösste Laibungstiefe je Seite vertiefter Öffnungen; flacher (bis REVEAL_MIN_DEPTH_MM), wenn der Kern sonst zu dünn
    # wäre. Höchstens 0.35 mm: Vom Sturz (Extrusionslinie 0.4 mm) liegen so mindestens 0.05 mm auf, er hängt nicht frei.
    reveal_depth_mm: float = 0.35
    # Wandkern, der hinter einer Laibung mindestens stehen bleibt; wirksam max(Profil, dieser Wert).
    # 0.8 mm = 2 Extrusionslinien: Ein Kern aus einer einzigen Linie (0.4 mm) war im Testdruck zu dünn.
    min_core_reveal_mm: float = 0.8
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


def check_scale_parameter(name: str, value) -> float:
    """Eigener Wert eines Massstab-Parameters als Zahl; ein nicht einstellbarer Name oder ein Wert ausserhalb
    der Grenzen von ``EDITABLE_PARAMETERS`` ist ein Fehler."""
    if name not in EDITABLE_PARAMETERS:
        raise ValueError(f"Parameter «{name}» ist nicht einstellbar")
    label, low, high = EDITABLE_PARAMETERS[name]
    try:
        number = math.nan if isinstance(value, bool) else float(value)
    except (TypeError, ValueError):
        number = math.nan
    if not low <= number <= high:
        raise ValueError(f"{label}: {low:g} bis {high:g} mm")
    return number


def split_key(key: str) -> tuple[str, str]:
    """«IfcWall[aussen]» → («IfcWall», «aussen»); ohne Bedingung → («IfcWall», «»)."""
    if key.endswith("]") and "[" in key:
        base, condition = key[:-1].split("[", 1)
        return base, condition
    return key, ""


def rule_class(key: str) -> str:
    """Klasse, für die ein Schlüssel gilt: «IfcCovering.CLADDING[aussen]» → «IfcCovering» («Ganzes/Teil» bleibt)."""
    return split_key(key)[0].split(".")[0]


def check_key(key: str) -> str:
    """Gibt den Schlüssel zurück; eine unbekannte oder falsch geschriebene Bedingung ist ein Fehler."""
    base, condition = split_key(key)
    if "[" in base or "]" in base or key.endswith("[]"):
        raise ValueError(f"«{key}»: Bedingung in eckigen Klammern am Ende, z.B. «IfcWall[aussen]»")
    if not condition:
        return key
    name, _, value = condition.partition(":")
    if name not in CONDITIONS:
        raise ValueError(f"Unbekannte Bedingung «{condition}» – erlaubt: {', '.join(CONDITIONS)}")
    if name == "duenner_als":
        try:
            ok = 0 < float(value) < math.inf
        except ValueError:
            ok = False
        if not ok:
            raise ValueError(f"«{condition}»: Grenzwert in mm fehlt, z.B. «duenner_als:0.8»")
    elif value:
        raise ValueError(f"Bedingung «{name}» hat keinen Wert")
    return key


def condition_label(condition: str) -> str:
    """Beschriftung für die Oberfläche: «duenner_als:0.8» → «dünner als 0.8 mm»."""
    name, _, value = condition.partition(":")
    return CONDITIONS.get(name, name).format(value)


def _condition_order(condition: str) -> tuple[int, float]:
    name, _, value = condition.partition(":")
    return list(CONDITIONS).index(name), float(value or 0)


def condition_met(condition: str, element: dict) -> bool:
    """Erfüllt das Bauteil (is_external, load_bearing, thickness_model_mm) die Bedingung?"""
    name, _, value = condition.partition(":")
    if name == "duenner_als":
        thickness = element.get("thickness_model_mm")
        return thickness is not None and thickness == thickness and thickness < float(value)    # NaN ≠ NaN
    if name == "tragend":
        return element.get("load_bearing") is True
    return element.get("is_external") is (name == "aussen")


@lru_cache(maxsize=None)
def _seed_rule_rows() -> tuple[dict, ...]:
    with DEFAULT_CSV.open(encoding="utf-8", newline="") as f:
        return tuple(csv.DictReader(f))


def row_scales(row: dict) -> tuple[str, ...]:
    """Massstäbe einer Zeile der regeln.csv («alle» oder «1:500,1:200»); ein unbekannter Massstab ist ein Fehler."""
    if row["scales"] == ALL_SCALES:
        return tuple(SCALES)
    scales = tuple(s.strip() for s in row["scales"].split(","))
    if unknown := [s for s in scales if s not in SCALES]:
        raise ValueError(f"regeln.csv, {row['ifc_class_name']}: unbekannter Massstab {', '.join(unknown)}")
    return scales


@lru_cache(maxsize=None)
def _seed_rules(scale: str) -> tuple[dict, ...]:
    chosen: dict[str, tuple[int, dict]] = {}
    for row in _seed_rule_rows():
        scales = row_scales(row)
        if scale not in scales:
            continue
        key = row["ifc_class_name"]
        if key in chosen and chosen[key][0] == len(scales):
            raise ValueError(f"regeln.csv: «{key}» für {scale} doppelt (gleich viele Massstäbe)")
        if key not in chosen or len(scales) < chosen[key][0]:
            chosen[key] = (len(scales), row)
    return tuple({"ruleset_name": scale, "ifc_class_name": key, "action": row["action"],
                  "category": row["category"], "reason": row.get("reason") or ""}
                 for key, (_, row) in chosen.items())


def seed_rules(scale: str) -> list[dict]:
    """Standardregeln eines Massstabs: [{ruleset_name, ifc_class_name, action, category, reason}].

    Je Schlüssel gilt die Zeile mit den wenigsten Massstäben (Abweichung vor «alle»). Einzige Stelle, die
    regeln.csv auswertet – für Ruleset.default, rule_reason, die Datenbank und docs/REFERENZ.md.
    """
    return [dict(z) for z in _seed_rules(LEGACY_RULE_SETS.get(scale, scale))]


def _standard_rules(scale: str) -> dict[str, tuple[str, str]]:
    """Standardregeln eines Massstabs: Regelschlüssel → (Aktion, Begründung)."""
    return {z["ifc_class_name"]: (z["action"], z["reason"]) for z in _seed_rules(scale)}


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
        self.rules = {check_key(k): check_action(a) for k, a in rules.items()}
        self.categories = categories or {}
        self.scale = LEGACY_RULE_SETS.get(scale, scale)
        self.parameter = parameter or ScaleParameters.default(self.scale)
        # Schlüssel ohne Bedingung → [(Bedingung, Schlüssel)] in der Reihenfolge des Vorrangs
        self.conditional: dict[str, list[tuple[str, str]]] = {}
        for key in self.rules:
            base, condition = split_key(key)
            if condition:
                self.conditional.setdefault(base, []).append((condition, key))
        for variants in self.conditional.values():
            variants.sort(key=lambda v: _condition_order(v[0]))

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
        rows = seed_rules(scale)
        if not rows:
            raise ValueError(f"Unbekannter Massstab «{scale}»")
        return cls.from_rows(rows, scale)

    def rule_source(self, ifc_class: str, predefined_type: str = "", schema: str | None = None, aggregate: str = "",
                    element: dict | None = None) -> str | None:
        """Regelschlüssel, der für das Bauteil gilt, oder None (keine Regel → entfernen).

        Reihenfolge: «Ganzes/Teil» → Regel des Ganzen → Regel des Teils; je über die Vererbungskette.
        ``element``: Eigenschaften für Bedingungen (is_external, load_bearing, thickness_model_mm), sonst keine.
        """
        element = element or {}
        part = class_chain(ifc_class, schema)
        if aggregate:
            aggregate_whole = class_chain(aggregate, schema)
            for g in aggregate_whole:
                for k in part:
                    if (key := self._match(f"{g}/{k}", element)) is not None:
                        return key
            if (key := self._key(aggregate_whole, "", element)) is not None:
                return key
        return self._key(part, predefined_type, element)

    def _key(self, chain: tuple[str, ...], predefined_type: str, element: dict) -> str | None:
        for k in chain:
            for base in ((f"{k}.{predefined_type}",) if predefined_type else ()) + (k,):
                if (key := self._match(base, element)) is not None:
                    return key
        return None

    def _match(self, base: str, element: dict) -> str | None:
        """Der Schlüssel ``base`` mit der ersten erfüllten Bedingung, sonst ``base`` selbst, sonst None."""
        for condition, key in self.conditional.get(base, ()):
            if condition_met(condition, element):
                return key
        return base if base in self.rules else None

    def action(self, ifc_class: str, predefined_type: str = "", schema: str | None = None, aggregate: str = "",
               element: dict | None = None) -> str:
        return self.rules.get(self.rule_source(ifc_class, predefined_type, schema, aggregate, element), "entfernen")

    def category(self, ifc_class: str, predefined_type: str = "", schema: str | None = None, aggregate: str = "",
                 element: dict | None = None) -> str:
        return self.categories.get(self.rule_source(ifc_class, predefined_type, schema, aggregate, element), "Sonstiges")

    def reason(self, key: str) -> str:
        """Begründung der Regel ``key`` (siehe ``rule_reason``)."""
        return rule_reason(self.scale, key, self.rules.get(key, ""))

    def classify(self, df: pd.DataFrame, schema: str | None = None) -> pd.DataFrame:
        """Ergänzt die Bauteiltabelle um action, is_printed, category, rule und reason (gibt eine Kopie zurück).

        ``rule``: der wirksame Regelschlüssel («» = keine Regel, entfernt); ``reason``: seine Begründung. Mit ``schema`` gilt
        die Vererbung; eine Spalte ``aggregate`` (Klasse des Aggregats) aktiviert die Aggregat-Regel. Bedingungen lesen
        die Spalten is_external, load_bearing und thickness_min_mm (real, geteilt durch den Massstab), sofern vorhanden.
        """
        df = df.copy()
        empty = pd.Series("", index=df.index)
        rows = zip(df["ifc_class"], df["predefined_type"] if "predefined_type" in df else empty,
                   df["aggregate"] if "aggregate" in df else empty, self._elements(df))
        rule = [self.rule_source(k, t, schema, g, e) for k, t, g, e in rows]
        df["action"] = [self.rules.get(r, "entfernen") for r in rule]
        df["category"] = [self.categories.get(r, "Sonstiges") for r in rule]
        df["rule"] = [r or "" for r in rule]
        df["reason"] = df["rule"].map({r: self.reason(r) for r in set(df["rule"])})
        df["is_printed"] = df["action"].isin(PRINTED_ACTIONS)
        return df

    def _elements(self, df: pd.DataFrame) -> list[dict]:
        """Eigenschaften je Bauteil für die Bedingungen (leer, wenn das Regelwerk keine hat)."""
        if not self.conditional:
            return [{}] * len(df)
        none = [None] * len(df)
        thickness = (df["thickness_min_mm"] / self.parameter.denominator).tolist() if "thickness_min_mm" in df else none
        return [{"is_external": _flag(x), "load_bearing": _flag(t), "thickness_model_mm": d}
                for x, t, d in zip(df["is_external"] if "is_external" in df else none,
                                   df["load_bearing"] if "load_bearing" in df else none, thickness)]


def _flag(value) -> bool | None:
    """Wahrheitswert aus einer Tabellenzelle: True, False oder None (fehlt, NaN)."""
    if value is None or pd.isna(value):
        return None
    return bool(value)
