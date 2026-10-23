"""Regressions-Netz: misst Qualitäts-Metriken des STL-Outputs für ein IFC.

Zweck:   VOR einer Änderung eine Baseline einfrieren (``--save``), NACH der Änderung erneut
         laufen lassen und vergleichen (``--compare``). So zeigt sich objektiv, ob eine Änderung
         ein Fort- oder Rückschritt ist – statt nur visuell zu raten.
Eingabe: ein IFC (``--ifc``, Standard NEST) oder alle IFC in testdaten/ (``--all``)
Ausgabe: Metriken als JSON (scripts/_baseline*.json) bzw. die Unterschiede zur Baseline

Gemessen wird pro Modell:
  * gedruckte Bauteile je IFC-Klasse (fängt z.B. versehentlich gedruckte Möbel)
  * Gesamt-Hülle: watertight, Volumen [cm³], gefüllte Voxel
  * je Geschoss: watertight, Dreiecke, Volumen, BBox [mm]

Aufruf (aus Projektwurzel, venv aktiv):
    python scripts/baseline_metrics.py --save
    python scripts/baseline_metrics.py --compare
    python scripts/baseline_metrics.py --all --compare
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))   # Skript direkt ausführbar (python scripts/...)

from config import QUALITIES
from core import pipeline
from core.analysis.ruleset import Ruleset
from core.ifc.model import IfcModel

IFC_DEFAULT = PROJECT_ROOT / "testdaten" / "ARC_Modell_NEST_230328.ifc"
BASELINE_JSON = PROJECT_ROOT / "scripts" / "_baseline.json"
SCALE = 200
# Festes Profil und Material, damit die Baseline nicht von der Datenbank abhängt
PROFILE = {"name": "baseline", "min_wall_mm": 0.8, "layer_height_mm": 0.2,
          "build_volume_x_mm": 250.0, "build_volume_y_mm": 210.0, "build_volume_z_mm": 220.0}
MATERIAL = {"name": "PLA", "density_g_cm3": 1.24, "price_chf_kg": 25.0}


def _mesh_metrics(mesh) -> dict:
    return {
        "watertight": bool(mesh.is_watertight),
        "dreiecke": int(len(mesh.faces)),
        "volumen_cm3": round(float(mesh.volume) / 1000.0, 2),
        "bbox_mm": [round(float(v), 1) for v in mesh.extents],
    }


def compute_metrics(ifc_path: Path) -> dict:
    ifc = IfcModel.open_file(ifc_path)
    df = pipeline.analyse(ifc, Ruleset.default(), SCALE, PROFILE)
    res = pipeline.generate(ifc, df, scale=SCALE, pitch_mm=QUALITIES["fein"],
                            profile=PROFILE, material=MATERIAL)
    return {
        "ifc": ifc_path.name,
        "gedruckte_bauteile_je_klasse": df[df["is_printed"]].groupby("ifc_class").size().sort_index().to_dict(),
        "gedruckt_total": int(df["is_printed"].sum()),
        "huelle_gesamt": {"watertight": res.watertight, "volumen_cm3": round(res.volume_cm3, 2),
                          "voxel": int(res.voxel_grid.matrix.sum())},
        "fugen_warnungen": res.warnings,
        "geschosse": {name: _mesh_metrics(m) for name, m in res.parts.items()},
    }


def _diff(old: dict, new: dict) -> list[str]:
    rows = []

    def compare(key_path, a, b):
        if isinstance(a, dict) or isinstance(b, dict):
            a, b = a or {}, b or {}
            for k in sorted(set(a) | set(b)):
                compare(f"{key_path}.{k}", a.get(k), b.get(k))
        elif a != b:
            rows.append(f"  {key_path}: {a!r} -> {b!r}")

    compare("", old, new)
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ifc", type=Path, default=IFC_DEFAULT)
    p.add_argument("--all", action="store_true", help="alle IFC in testdaten/ (je _baseline_<name>.json)")
    p.add_argument("--save", action="store_true", help="Baseline schreiben")
    p.add_argument("--compare", action="store_true", help="gegen Baseline vergleichen")
    args = p.parse_args()
    if args.all:
        for ifc in sorted((PROJECT_ROOT / "testdaten").glob("*.ifc")):
            print(f"--- {ifc.name}", flush=True)
            try:
                _single(ifc, BASELINE_JSON.with_name(f"_baseline_{ifc.stem}.json"), args, output=False)
            except Exception as error:      # ein kaputtes Modell soll die übrigen nicht aufhalten
                print(f"  FEHLER: {error!r}", flush=True)
    else:
        _single(args.ifc, BASELINE_JSON, args)


def _single(ifc: Path, store: Path, args, output: bool = True) -> None:
    m = compute_metrics(ifc)
    if output:
        print(json.dumps(m, indent=2, ensure_ascii=False))
    if args.save:
        store.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nBaseline gespeichert: {store}", flush=True)
    elif args.compare:
        if not store.exists():
            print(f"\nKeine Baseline für {ifc.name} – erst mit --save erzeugen.")
            return
        old = json.loads(store.read_text(encoding="utf-8"))
        diff = _diff(old, json.loads(json.dumps(m)))
        print(f"\n=== Vergleich zur Baseline: {ifc.name} ===")
        print("\n".join(diff) if diff else "  identisch", flush=True)


if __name__ == "__main__":
    main()
