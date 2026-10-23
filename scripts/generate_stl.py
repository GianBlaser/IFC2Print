"""Kommandozeile ohne Oberfläche: IFC → Analyse → STL je Geschoss + Report.

Zweck:   zeigt, dass die Verarbeitung (core/) unabhängig von der NiceGUI-Oberfläche läuft.
Eingabe: IFC-Datei, optional --scale, --quality, --output
Ausgabe: <name>_geschosse.zip (STL je Teil) und <name>_report.pdf im Ausgabeordner

    python scripts/generate_stl.py testdaten/MFH_eBKPH_Test.ifc --scale 1:200 --quality entwurf
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # Projektordner importierbar

from config import SCALES, QUALITIES
from core import pipeline
from core.analysis.ruleset import Ruleset, ScaleParameters
from core.ifc.model import IfcModel
from db.database import DEFAULT_PATH, Database


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ifc", type=Path)
    p.add_argument("--scale", choices=list(SCALES), default="1:200")
    p.add_argument("--quality", choices=list(QUALITIES), default="fein")
    p.add_argument("--output", type=Path, default=Path("output"))
    args = p.parse_args(argv)

    db = Database(os.environ.get("IFC2PRINT_DB", DEFAULT_PATH))   # wie app.py: Tests setzen eine Temp-DB
    profile, material = db.profiles()[0], db.materials()[0]
    scale = SCALES[args.scale]
    # Regeln und Parameter gehören zum Massstab – dieselben wie in der Oberfläche (eigene Regeln inklusive)
    parameter = ScaleParameters.from_row(db.scale_parameters(args.scale))
    ruleset = Ruleset.from_rows(db.rules(args.scale), args.scale, parameter)

    t = time.perf_counter()
    ifc = IfcModel.open_file(args.ifc)
    df = pipeline.analyse(ifc, ruleset, scale, profile)
    print(f"{ifc.schema}: {len(df)} Bauteile, {int(df['is_printed'].sum())} gedruckt, "
          f"Status: {df['status'].value_counts().to_dict()}  ({time.perf_counter() - t:.1f} s)")

    t = time.perf_counter()
    res = pipeline.generate(ifc, df, scale=scale, pitch_mm=QUALITIES[args.quality],
                            profile=profile, material=material, parameter=parameter,
                            progress=lambda phase, a: print(f"\r{a:4.0%} {phase:<30}", end=""))
    print(f"\nHülle: {len(res.parts)} Teile, wasserdicht={res.watertight}, {res.volume_cm3:.1f} cm³, "
          f"{res.grams:.0f} g, CHF {res.cost_chf:.2f}, {res.time_h:.1f} h  ({time.perf_counter() - t:.1f} s)")

    args.output.mkdir(parents=True, exist_ok=True)
    base_name = args.ifc.stem
    (args.output / f"{base_name}_geschosse.zip").write_bytes(res.stl_zip(base_name))
    (args.output / f"{base_name}_report.pdf").write_bytes(res.report_pdf(df))
    print(f"Geschrieben nach {args.output}/")


if __name__ == "__main__":
    main()
