#!/usr/bin/env python3
"""
One-command pipeline: rotation-report PDF -> flights.json -> combined LIR PDF.

Usage:
    python3 run_lir.py --input Rotation_report.pdf --output loading_instructions.pdf \
        --station BGY --date-format "%d/%m/%Y"

This just chains parse_rotation_report.parse_pdf() and generate_lir.generate_lir_pdf() so you
don't need two separate commands. Everything each of those scripts prints (parse summary,
warnings, skipped flights) still gets printed here -- nothing is hidden.

If your input isn't the rotation-report PDF layout parse_rotation_report.py expects, build your
own flights.json (see generate_lir.py's docstring for the schema) and call generate_lir.py
directly instead of this script.
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from paths import get_base_dir  # noqa: E402
from parse_rotation_report import parse_pdf  # noqa: E402
from generate_lir import generate_lir_pdf, load_json  # noqa: E402

BASE_DIR = get_base_dir()
SCRIPT_DIR = BASE_DIR / "scripts"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Path to the rotation-report PDF")
    ap.add_argument("--output", required=True, help="Path to write the combined LIR PDF")
    ap.add_argument("--config", default=str(SCRIPT_DIR / "aircraft_config.json"))
    ap.add_argument("--timezones", default=str(SCRIPT_DIR / "airport_timezones.json"))
    ap.add_argument("--carriers", default=str(SCRIPT_DIR / "carrier_codes.json"))
    ap.add_argument(
        "--date-format",
        default="%d/%m/%Y",
        help="strftime format for the Date field printed on the form. Default is DD/MM/YYYY.",
    )
    ap.add_argument(
        "--station",
        default=None,
        help="If set (e.g. BGY), only flights DEPARTING from this station get a page.",
    )
    ap.add_argument(
        "--save-json",
        default=None,
        help="Optional: also save the intermediate flights.json to this path, for inspection.",
    )
    args = ap.parse_args()

    print(f"Parsing {args.input} ...")
    flights, unmatched = parse_pdf(args.input)
    print(f"Parsed {len(flights)} flight(s).")
    if unmatched:
        print(f"\n{len(unmatched)} line(s) in the PDF could not be read as a flight row:")
        for line in unmatched:
            print(f"  - {line}")
        print(
            "(Expected for report headers/footers. If a real flight row is listed above, the "
            "report layout has changed and parse_rotation_report.py needs a small fix.)\n"
        )

    if args.save_json:
        import json

        Path(args.save_json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump(flights, f, indent=2)
        print(f"Saved intermediate flights.json -> {args.save_json}")

    config = load_json(args.config)
    tz_table = load_json(args.timezones)
    tz_table = {k: v for k, v in tz_table.items() if not k.startswith("_")}
    carrier_map = load_json(args.carriers)
    carrier_map = {k: v for k, v in carrier_map.items() if not k.startswith("_")}

    print(f"\nGenerating LIR PDF{f' for {args.station} departures' if args.station else ''} ...")
    writer, warnings, skipped, generated = generate_lir_pdf(
        flights, config, tz_table, carrier_map, station=args.station, date_format=args.date_format
    )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "wb") as f:
        writer.write(f)

    print(f"\nGenerated {generated} page(s) -> {args.output}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  - {w}")
    if skipped:
        print(f"\n{len(skipped)} flight(s) skipped (no page generated):")
        for s in skipped:
            print(f"  - {s}")
    if not warnings and not skipped and not unmatched:
        print("No warnings.")


if __name__ == "__main__":
    main()
