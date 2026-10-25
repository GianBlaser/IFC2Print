"""Prüfpunkte: Fälle, die sonst unbemerkt ein falsches Modell ergäben – für die Oberfläche und den Bericht.

Zweck:   Macht sichtbar, was beim Erzeugen anders läuft als erwartet (fehlende Regeln, Umgebung, Ausreisser,
         defekte Geometrie, Versatz, fehlende Georeferenz) – strukturiert (``check_points``) oder als Sätze (``checklist``).
Eingabe: IFC-Modell und Bauteiltabelle (core.pipeline.analyse).
Ausgabe: Liste von Prüfpunkten (Dictionaries) bzw. Liste von Sätzen.
"""

import pandas as pd

from core.ifc.assignment import room_names
from core.ifc.model import IfcModel
from core.ifc.schema import class_chain

# Karte im Blatt 05 Prüfen, in der ein Prüfpunkt erscheint (Schlüssel = ``kind``)
_CATEGORY = {"keine": "regeln", "geerbt": "regeln", "aggregate": "regeln", "storeys": "storeys",
             "ausreisser": "ausreisser", "umgebung": "umgebung", "geometry": "geometry", "versatz": "georeferenz",
             "georeferenz": "georeferenz", "oeffnungen": "lauf", "gefaelle": "lauf"}   # lauf: nur im Ergebnis

# Was tun je ``kind`` – Spalte «Was tun» im PDF-Report
_FIX = {"keine": "Regeln im Blatt 03 ergänzen", "geometry": "IFC-Geometrie im Autorenwerkzeug prüfen",
        "geerbt": "Keine Aktion; Regel bei Bedarf eigens setzen", "aggregate": "Keine Aktion",
        "storeys": "Keine Aktion", "ausreisser": "Im Blatt 03 je Bauteil übersteuern",
        "umgebung": "Im Blatt 03 je Bauteil übersteuern", "versatz": "Keine Aktion; Lage bleibt im IFC",
        "oeffnungen": "Keine Aktion", "gefaelle": "Keine Aktion"}

_SENTENCE_TEMPLATE = {"keine": "Ohne Regel, nicht gedruckt: {e} – im Regelblatt einstellbar.",
                      "geerbt": "Ohne eigene Regel, von der Oberklasse übernommen: {e}.",
                      "aggregate": "Teile folgen der Regel ihres Ganzen: {e}.",
                      "storeys": "Doppelte Geschossnamen unterschieden: {e}.",
                      "oeffnungen": "{n} Öffnungen ohne Fenster oder Tür ausgeschnitten (Treppenaugen, Schächte, Durchgänge).",
                      "gefaelle": "{n} Decken/Dächer mit Gefälle eben gemacht (tiefste bis höchste Stelle gefüllt)."}

# Prüfpunkte zur Herkunft der Regel: (kind, Titel, Erklärung)
_RULE_KINDS = (
    ("keine", "Ohne Regel, nicht gedruckt",
     "Für diese Klassen gibt es keine Regel – sie fehlen im Druck. Im Regelblatt einstellbar."),
    ("geerbt", "Regel von der Oberklasse übernommen",
     "Keine eigene Regel; es gilt die Regel der allgemeineren IFC-Klasse."),
    ("aggregate", "Teile folgen ihrem Ganzen",
     "Bauteile eines Aggregats (z.B. Treppenlauf in einer Treppe) folgen dessen Regel."),
)


def check_points(ifc: IfcModel, df: pd.DataFrame) -> list[dict]:
    """Fälle, die sonst unbemerkt ein falsches Modell ergäben – strukturiert für die Oberfläche.

    Je Punkt: ``kind`` (keine | geerbt | aggregate | storeys | ausreisser | umgebung | geometry | versatz | georeferenz),
    ``category`` (Karte im Blatt 05 Prüfen: regeln | storeys | ausreisser | umgebung | geometry | georeferenz),
    ``title``, ``explanation``, ``entries`` [(Text, Anzahl oder None)], ``target`` (Blatt zum Beheben oder None)
    und ``fix`` (Was tun, für den PDF-Report).
    """
    points = (_rule_points(ifc, df) + _storey_name_points(ifc) + _outlier_points(df) + _surroundings_points(df)
              + _geometry_points(df) + _offset_points(ifc) + _georeference_points(ifc))
    for p in points:
        p["category"] = _CATEGORY[p["kind"]]
    return points


def _point(kind: str, title: str, explanation: str, entries: list, target: str | None = None) -> dict:
    """Ein Prüfpunkt als Dictionary (``category`` setzt ``check_points`` zuletzt)."""
    return dict(kind=kind, title=title, explanation=explanation, entries=entries, target=target,
                fix=_FIX.get(kind, "Keine Aktion"))


def run_points(cut: dict[str, int], flattened: dict[str, int]) -> list[dict]:
    """Prüfpunkte aus dem Erzeugungslauf, je IFC-Klasse gezählt: Öffnungen ohne Fenster oder Tür, eben gemachte Decken."""
    points = []
    if cut:
        points.append(_point("oeffnungen", "Öffnungen ohne Fenster oder Tür ausgeschnitten",
                             "Treppenaugen, Schächte und Durchgänge bleiben offen wie im IFC.", sorted(cut.items())))
    if flattened:
        points.append(_point("gefaelle", "Decken mit Gefälle eben gemacht",
                             "Tiefste bis höchste Stelle gefüllt, damit die Decke ohne Treppenstufen druckt.",
                             sorted(flattened.items())))
    for p in points:
        p["category"] = _CATEGORY[p["kind"]]
    return points


def _rule_source(z: tuple, schema_id: str) -> str:
    """Woher die Regel eines Bauteils stammt: keine | own | aggregate (Regel des Ganzen) | geerbt (Oberklasse)."""
    if not z.rule:
        return "keine"
    if z.rule.split(".")[0] == z.ifc_class:
        return "own"
    return "aggregate" if getattr(z, "aggregate", "") and z.rule.split("/")[0].split(".")[0] in \
        class_chain(z.aggregate, schema_id) else "geerbt"


def _rule_points(ifc: IfcModel, df: pd.DataFrame) -> list[dict]:
    """Klassen ohne eigene Regel: ganz ohne Regel, von der Oberklasse oder vom Ganzen übernommen."""
    if "rule" not in df:
        return []
    sources = pd.Series([_rule_source(z, ifc.schema_id) for z in df.itertuples()], index=df.index)
    points = []
    for kind, title, explanation in _RULE_KINDS:
        part = df[sources == kind]
        if part.empty:
            continue
        if kind == "keine":
            entries = [(k, int(n)) for k, n in part["ifc_class"].value_counts().sort_index().items()]
        else:
            entries = [(f"{k} → {r}", int(n)) for (k, r), n in part.groupby(["ifc_class", "rule"]).size().items()]
        points.append(_point(kind, title, explanation, entries, target="regeln"))
    return points


def _storey_name_points(ifc: IfcModel) -> list[dict]:
    """Geschosse, die wegen gleicher Namen umbenannt wurden."""
    names = room_names(ifc.model)
    renamed = [(f"«{s.Name}» → «{names[s.id()]}»", None) for s in ifc.model.by_type("IfcBuildingStorey")
               if names[s.id()] != (s.Name or "unbekannt")]
    if not renamed:
        return []
    return [_point("storeys", "Doppelte Geschossnamen unterschieden",
                   "Gleich benannte Geschosse wurden eindeutig umbenannt.", renamed)]


def _outlier_points(df: pd.DataFrame) -> list[dict]:
    """Bauteile weit ausserhalb des Gebäudes (nicht gedruckt)."""
    if not (n := int((df["category"] == "Ausreisser").sum())):
        return []
    return [_point("ausreisser", f"{n} Ausreisser nicht gedruckt",
                   "Bauteile weit ausserhalb des Gebäudes – je Bauteil in der Tabelle übersteuerbar.", [])]


def _surroundings_points(df: pd.DataFrame) -> list[dict]:
    """Bauteile, die als Gelände oder Stützmauer erkannt wurden (nicht gedruckt)."""
    surroundings_df = df[df["category"] == "Umgebung"]
    if not len(surroundings_df):
        return []
    entries = [(k, int(n)) for k, n in surroundings_df["ifc_class"].value_counts().sort_index().items()]
    return [_point("umgebung", f"{len(surroundings_df)} Bauteile als Umgebung nicht gedruckt",
                   "Name, Typ oder Layer deuten auf Gelände oder Stützmauer hin "
                   "– je Bauteil in der Tabelle übersteuerbar.", entries)]


def _geometry_points(df: pd.DataFrame) -> list[dict]:
    """Bauteile ohne Geometrie oder mit defekter Geometrie."""
    if "geometry" not in df or not (problems := df[df["geometry"] != "ok"]).size:
        return []
    entries = [(f"{k} · {'ohne Geometrie' if g == 'fehlt' else 'defekt'}", int(n))
               for (k, g), n in problems.groupby(["ifc_class", "geometry"]).size().items()]
    return [_point("geometry", f"{len(problems)} Bauteile ohne oder mit defekter Geometrie",
                   "Flache, degenerierte oder fehlende Geometrie – im Viewer rot, im Druck "
                   "nicht oder nur teilweise vorhanden.", entries)]


def _offset_points(ifc: IfcModel) -> list[dict]:
    """Modell in Landeskoordinaten: für den Export verschoben."""
    if not ifc.offset_mm.any():
        return []
    x, y, _ = ifc.offset_mm / 1000
    return [_point("versatz", "Modell in Landeskoordinaten",
                   f"Für den Export um {x:,.0f} m / {y:,.0f} m verschoben.".replace(",", "'"), [])]


def _georeference_points(ifc: IfcModel) -> list[dict]:
    """Lage oder Nordrichtung fehlen im Modell."""
    if not (missing_info := georeference_gaps(ifc)):
        return []
    return [_point("georeferenz", "Georeferenz unvollständig",
                   "Für den Druck ohne Belang; Kontextmodelle oder Besonnungsstudien brauchen "
                   "Lage und Nordrichtung.", [(f, None) for f in missing_info])]


def georeference_gaps(ifc: IfcModel) -> list[str]:
    """Was zur Georeferenz fehlt (Schema-Lookup ohne Geometrie): Lage und Nordrichtung.

    IFC4: IfcMapConversion; IFC2x3 kennt sie nicht – dort zählen RefLatitude/RefLongitude der IfcSite.
    """
    m = ifc.model
    missing_info = []
    if ifc.schema_id.upper().startswith("IFC2X3"):
        if not any(s.RefLatitude and s.RefLongitude for s in m.by_type("IfcSite")):
            missing_info.append("Lage: IfcSite ohne RefLatitude/RefLongitude")
    elif not m.by_type("IfcMapConversion"):
        missing_info.append("Lage: keine IfcMapConversion")
    contexts = [k for k in m.by_type("IfcGeometricRepresentationContext")
                if not k.is_a("IfcGeometricRepresentationSubContext")]
    if not any(k.TrueNorth for k in contexts):
        missing_info.append("Nordrichtung: TrueNorth nicht gesetzt")
    return missing_info


def for_print(points: list[dict]) -> list[dict]:
    """Die Prüfpunkte, die den Druck betreffen: ohne fehlende Georeferenz (der Versatz zählt)."""
    return [p for p in points if p["category"] != "georeferenz" or p["kind"] == "versatz"]


def sentence(point: dict) -> str:
    """Ein Prüfpunkt als Satz (Warnungen des Ergebnisses)."""
    e = ", ".join(t if n is None else f"{t} ({n})" for t, n in point["entries"])
    n = sum(1 if c is None else c for _, c in point["entries"])
    if point["kind"] in _SENTENCE_TEMPLATE:
        return _SENTENCE_TEMPLATE[point["kind"]].format(e=e, n=n)
    return f"{point['title']}. {point['explanation']}"


def checklist(ifc: IfcModel, df: pd.DataFrame) -> list[str]:
    """Prüfpunkte als Sätze (Warnungen des Ergebnisses)."""
    return [sentence(p) for p in for_print(check_points(ifc, df))]
