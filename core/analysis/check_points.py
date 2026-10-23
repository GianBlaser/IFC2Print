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
             "georeferenz": "georeferenz"}

_SENTENCE_TEMPLATE = {"keine": "Ohne Regel, nicht gedruckt: {e} – im Regelblatt einstellbar.",
                      "geerbt": "Ohne eigene Regel, von der Oberklasse übernommen: {e}.",
                      "aggregate": "Teile folgen der Regel ihres Ganzen: {e}.",
                      "storeys": "Doppelte Geschossnamen unterschieden: {e}."}

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
    ``title``, ``explanation``, ``entries`` [(Text, Anzahl oder None)] und ``target`` (Blatt zum Beheben oder None).
    """
    points = (_rule_points(ifc, df) + _storey_name_points(ifc) + _outlier_points(df) + _surroundings_points(df)
              + _geometry_points(df) + _offset_points(ifc) + _georeference_points(ifc))
    for p in points:
        p["category"] = _CATEGORY[p["kind"]]
    return points


def _point(kind: str, title: str, explanation: str, entries: list, target: str | None = None) -> dict:
    """Ein Prüfpunkt als Dictionary (``category`` setzt ``check_points`` zuletzt)."""
    return dict(kind=kind, title=title, explanation=explanation, entries=entries, target=target)


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


def checklist(ifc: IfcModel, df: pd.DataFrame) -> list[str]:
    """Prüfpunkte als Sätze (Warnungen des Ergebnisses, PDF)."""
    sentences = []
    for p in check_points(ifc, df):
        if p["category"] == "georeferenz" and p["kind"] != "versatz":   # für den Druck ohne Belang
            continue
        e = ", ".join(t if n is None else f"{t} ({n})" for t, n in p["entries"])
        sentences.append(_SENTENCE_TEMPLATE[p["kind"]].format(e=e) if p["kind"] in _SENTENCE_TEMPLATE else f"{p['title']}. {p['explanation']}")
    return sentences
