#!/usr/bin/env python3
"""
Parse a Wizz Air "Daily Flight Schedule Report" (rotation report) PDF into the flights.json
format that generate_lir.py consumes.

Usage:
    python3 parse_rotation_report.py --input Rotation_report.pdf --output flights.json

This is tuned to one specific report layout (the "Daily Flight Schedule Report for <station>
airport" export, with columns DATE FLIGHT TYP DEP DES STD STA [ETD] [ETA] REG ACT CAP PAX CPT,
all times in UTC, dates as M/D/YYYY). If the report format changes, the regex in
FLIGHT_LINE_RE below is the one place to fix.

It deliberately does NOT do timezone conversion, IATA carrier-code conversion, aircraft-type
mapping, or filtering by departure station -- generate_lir.py already does all of that from the
plain flights.json this produces. This script's only job is turning the PDF table into
structured data reliably.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

# DATE  ICAO NUM  TYP  DEP  DES  STD  STA  [ETD]  [ETA]  REG  ACT  CAP  PAX  CPT(rest of line)
FLIGHT_LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<icao>[A-Z]{2,3})\s+(?P<num>\d{2,5})\s+"
    r"(?P<typ>[A-Z])\s+"
    r"(?P<dep>[A-Z]{3})\s+(?P<des>[A-Z]{3})\s+"
    r"(?P<std>\d{2}:\d{2})\s+(?P<sta>\d{2}:\d{2})\s+"
    r"(?:\d{2}:\d{2}\s+)?(?:\d{2}:\d{2}\s+)?"  # optional ETD, optional ETA -- discarded
    r"(?P<reg>[0-9A-Z]+-[0-9A-Z]+)\s+"
    r"(?P<act>[0-9A-Z]{2,4})\s+"
    r"(?P<cap>\d+)\s+(?P<pax>\d+)\s+"
    r"(?P<cpt>.+)$"
)

SKIP_PREFIXES = (
    "Daily Flight Schedule Report",
    "Filtered by AOCs",
    "All times in UTC",
    "Changes are highlighted",
    "DATE FLIGHT",
    "Page ",
)


def iso_date(date_str):
    """Convert M/D/YYYY (as used in this report) to ISO YYYY-MM-DD."""
    m, d, y = date_str.split("/")
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def parse_pdf(path):
    flights = []
    unmatched = []

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if any(line.startswith(p) for p in SKIP_PREFIXES):
                    continue

                m = FLIGHT_LINE_RE.match(line)
                if not m:
                    unmatched.append(line)
                    continue

                flights.append(
                    {
                        "date": iso_date(m.group("date")),
                        "flight_number": f"{m.group('icao')} {m.group('num')}",
                        "dep": m.group("dep"),
                        "des": m.group("des"),
                        "std_utc": m.group("std"),
                        "reg": m.group("reg"),
                        "act": m.group("act"),
                    }
                )

    return flights, unmatched


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Path to the rotation-report PDF")
    ap.add_argument("--output", required=True, help="Path to write flights.json")
    args = ap.parse_args()

    flights, unmatched = parse_pdf(args.input)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(flights, f, indent=2)

    print(f"Parsed {len(flights)} flight(s) -> {args.output}")
    if unmatched:
        print(f"\n{len(unmatched)} line(s) could not be parsed as a flight row (shown below).")
        print("These are printed so you can check nothing real got silently dropped -- lines")
        print("like report headers/footers are expected here, but a real flight row that")
        print("failed to match means FLIGHT_LINE_RE needs adjusting for a layout change:")
        for line in unmatched:
            print(f"  - {line}")


if __name__ == "__main__":
    main()
