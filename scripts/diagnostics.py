"""Einmal-Diagnose für eine konkrete IFC: dünne Wände, Umgebung/Ausreisser, Fenster/Tür-Öffnungen.

Zweck:   schnell sehen, was ein unbekanntes IFC enthält, bevor man es erzeugt.
Eingabe: Pfad der IFC-Datei (python scripts/diagnostics.py testdaten/MFH_eBKPH_Test.ifc)
Ausgabe: Textbericht in der Konsole

Kein Voxelisieren – nur Import + Bauteiltabelle + Öffnungs-/Fill-Relationen.
"""
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # Projektordner importierbar

from config import SCALES, SCALE_DEFAULT, QUALITIES, QUALITY_DEFAULT
from core.analysis.ruleset import PRINTED_ACTIONS, Ruleset
from core.ifc.model import IfcModel

file_path = sys.argv[1]
scale = SCALES[SCALE_DEFAULT]
pitch = QUALITIES[QUALITY_DEFAULT]
print(f"Datei: {file_path}\nMassstab 1:{scale}  Pitch {pitch} mm  (Default)")

ifc = IfcModel.open_file(file_path)
df = ifc.building_elements.copy()
ruleset_obj = Ruleset.default()
df["action"] = [ruleset_obj.action(k, t) for k, t in zip(df["ifc_class"], df.get("predefined_type", ""))]
df["is_printed"] = df["action"].isin(PRINTED_ACTIONS)

print("\n== Bauteile je Klasse (gedruckt/gesamt) ==")
for cls_name in sorted(df["ifc_class"].unique()):
    part = df[df["ifc_class"] == cls_name]
    print(f"  {cls_name:28s} gedruckt {int(part['is_printed'].sum()):4d} / {len(part):4d}  aktion={part['action'].iloc[0]}")

# --- Dünne Wände ---
wall = df[(df["ifc_class"].str.startswith("IfcWall")) & df["is_printed"]].copy()
wall["thickness_model_mm"] = wall["thickness_min_mm"] / scale
print(f"\n== Dünnste gedruckte Wände (Modell-mm, 1 Voxel = {pitch} mm) ==")
for r in wall.nsmallest(12, "thickness_model_mm").itertuples():
    voxel = r.thickness_model_mm / pitch
    print(f"  {r.thickness_model_mm:6.2f} mm ({voxel:4.1f} Voxel)  real {r.thickness_min_mm:7.1f} mm  {r.ifc_class} '{r.name}' [{r.storey}]")

# --- Umgebung / Ausreisser (XY weit weg vom Median-Zentrum) ---
print("\n== Räumliche Ausreisser der GEDRUCKTEN Bauteile (mögliche Umgebung) ==")
printed_df = df[df["is_printed"]].dropna(subset=["bbox_x_mm"])
center_points = []
for r in printed_df.itertuples():
    g = ifc.geometry.get(r.guid)
    if g is not None:
        center_points.append(((g.verts.min(0) + g.verts.max(0)) / 2, r))
if center_points:
    center = np.median([c for c, _ in center_points], axis=0)
    dist = sorted(((float(np.hypot(*(c[:2] - center[:2]))), r) for c, r in center_points),
                  key=lambda t: t[0], reverse=True)
    for d, r in dist[:12]:
        print(f"  {d/1000:7.1f} m vom Zentrum  {r.ifc_class} '{r.name}' [{r.storey}]  bbox {r.bbox_x_mm/1000:.1f}x{r.bbox_y_mm/1000:.1f}x{r.bbox_z_mm/1000:.1f} m")

print("\n== Geschoss-Zuordnung (gedruckt) ==")
for g, n in Counter(df[df["is_printed"]]["storey"]).most_common():
    print(f"  {n:4d}  {g}")

# --- Öffnungen: Fenster vs. Tür über IfcRelFillsElement ---
print("\n== Öffnungen und ihre Füllung (Fenster/Tür) ==")
fill = {}
for rel in ifc.model.by_type("IfcRelFillsElement"):
    fill[rel.RelatingOpeningElement.GlobalId] = rel.RelatedBuildingElement.is_a()
void_in_wall = 0
counter = Counter()
for rel in ifc.model.by_type("IfcRelVoidsElement"):
    host = rel.RelatingBuildingElement
    if host.is_a("IfcSlab") or host.is_a("IfcRoof"):
        continue
    void_in_wall += 1
    counter[fill.get(rel.RelatedOpeningElement.GlobalId, "(ohne Füllung)")] += 1
print(f"  Öffnungen in Wänden gesamt: {void_in_wall}")
for k, n in counter.most_common():
    print(f"    {n:4d}  gefüllt von {k}")
