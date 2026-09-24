#!/usr/bin/env python3
"""
Generate a combined Loading Instruction Report (LIR) PDF from a list of flights.

Usage:
    python3 generate_lir.py --flights flights.json --output combined_lir.pdf

flights.json is a JSON array of objects with these fields (all strings):
    date          ISO format, e.g. "2026-09-07"
    flight_number e.g. "WMT 3131"
    dep           3-letter departure airport code, e.g. "BBU"
    des           3-letter destination airport code, e.g. "BGY"
    std_utc       "HH:MM" in UTC, as shown in the source schedule
    reg           aircraft registration, e.g. "HA-LXM"
    act           aircraft type code as shown in the schedule, e.g. "320", "321", "32Q"

Optional per-flight overrides (rarely needed -- only set these if the user gave you
flight-specific instructions that differ from the standard pattern):
    load_pattern  object mapping hold name -> PCS value, e.g. {"Cpl1": "80"}.
                  Any hold in the template NOT present in this map is filled with "NIL".
                  If omitted, the aircraft type's default_pattern from aircraft_config.json is used.

The script looks up aircraft_config.json (template + hold coordinates + default load pattern),
airport_timezones.json (for STD UTC -> STD LT conversion), and carrier_codes.json (ICAO -> IATA
flight-number prefix, e.g. "WMT 3131" -> "W4 3131") next to itself unless overridden with
--config / --timezones / --carriers.

It prints a summary of any flights it could NOT place on a template (unknown aircraft code)
and any STD (LT) values that fall back to raw UTC because the departure airport's timezone
is not in the reference table. Read that summary before handing the PDF over -- it's the
mechanism for catching bad input rather than silently printing something wrong on a page.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black
import io

from paths import get_base_dir

BASE_DIR = get_base_dir()
SCRIPT_DIR = BASE_DIR / "scripts"
SKILL_DIR = BASE_DIR


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def box_to_reportlab(box, page_height):
    """Convert a [x0, x1, top, bottom] box (measured from top of page, pdfplumber-style)
    into reportlab's (x0, x1, y0, y1) with origin at bottom-left."""
    x0, x1, top, bottom = box
    y1 = page_height - top
    y0 = page_height - bottom
    return x0, x1, y0, y1


def draw_centered(c, box, page_height, text, font="Helvetica-Bold", size=9.5):
    x0, x1, y0, y1 = box_to_reportlab(box, page_height)
    c.setFont(font, size)
    c.setFillColor(black)
    text_width = c.stringWidth(text, font, size)
    tx = x0 + ((x1 - x0) - text_width) / 2
    ty = y0 + (y1 - y0) / 2 - size * 0.35
    c.drawString(max(tx, x0 + 2), ty, text)


def draw_left(c, box, page_height, text, font="Helvetica-Bold", size=9.5, pad=4):
    x0, x1, y0, y1 = box_to_reportlab(box, page_height)
    c.setFont(font, size)
    c.setFillColor(black)
    ty = y0 + (y1 - y0) / 2 - size * 0.35
    c.drawString(x0 + pad, ty, text)


def compute_local_std(date_str, std_utc, dep_code, tz_table, warnings, flight_number):
    try:
        y, m, d = (int(p) for p in date_str.split("-"))
        hh, mm = (int(p) for p in std_utc.split(":"))
    except Exception:
        warnings.append(
            f"{flight_number}: could not parse date '{date_str}' / std_utc '{std_utc}' -- printing std_utc as-is."
        )
        return std_utc

    utc_dt = datetime.datetime(y, m, d, hh, mm, tzinfo=datetime.timezone.utc)

    tz_name = tz_table.get(dep_code)
    if not tz_name:
        warnings.append(
            f"{flight_number}: departure airport '{dep_code}' is not in airport_timezones.json -- "
            f"printed STD (LT) as raw UTC ({std_utc}Z). Add '{dep_code}' to the timezone table and "
            f"regenerate if you need the true local time."
        )
        return f"{std_utc}Z"

    local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
    return local_dt.strftime("%H:%M")


def convert_flight_number(flight_number, carrier_map, warnings):
    parts = flight_number.strip().split(" ", 1)
    if len(parts) != 2:
        return flight_number
    icao, number = parts
    iata = carrier_map.get(icao)
    if not iata:
        warnings.append(
            f"{flight_number}: ICAO carrier code '{icao}' is not in carrier_codes.json -- "
            f"printed as-is instead of converting to an IATA code. Add a mapping if this is "
            f"a genuine Wizz operator code."
        )
        return flight_number
    return f"{iata} {number}"


def format_date_display(date_iso, fmt, warnings, flight_number):
    try:
        y, m, d = (int(p) for p in date_iso.split("-"))
        return datetime.date(y, m, d).strftime(fmt)
    except Exception:
        warnings.append(
            f"{flight_number}: could not reformat date '{date_iso}' -- printing as-is."
        )
        return date_iso


def build_overlay(template_cfg, flight, local_std, display_flight_number, display_date, warnings):
    page_w, page_h = template_cfg["page_size"]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    hb = template_cfg["header_boxes"]
    route = f"{flight['dep']}-{flight['des']}"
    draw_centered(c, hb["route"], page_h, route)
    draw_centered(c, hb["flight_number"], page_h, display_flight_number)
    draw_centered(c, hb["registration"], page_h, flight["reg"])
    draw_centered(c, hb["date"], page_h, display_date)
    draw_centered(c, hb["std_lt"], page_h, local_std)
    # Load control signature box is intentionally left blank for a human signature.

    pattern = flight.get("load_pattern")
    if pattern is None:
        pattern = template_cfg.get("default_pattern")

    if pattern is None:
        warnings.append(
            f"{flight['flight_number']}: no standard load pattern is configured for "
            f"{template_cfg['label']} -- LOADING INSTRUCTION boxes left blank. Fill in "
            f"manually or add a default_pattern for this aircraft type once one is confirmed."
        )
    else:
        # Values go in the top "LOADING INSTRUCTION" diagram (one box per hold) -- this is
        # what tells ramp staff what to load. The bottom "LOADING REPORT" diagram's PCS/KGS
        # boxes are intentionally left blank for staff to fill in by hand after loading.
        for hold_name in template_cfg["hold_order"]:
            box = template_cfg["instruction_hold_boxes"][hold_name]
            value = pattern.get(hold_name, "NIL")
            draw_centered(c, box, page_h, value)

    c.save()
    buf.seek(0)
    return buf


def generate_lir_pdf(flights, config, tz_table, carrier_map, station=None, date_format="%d/%m/%Y"):
    """Core logic, callable directly (no subprocess) by run_lir.py or any other script.
    Returns (writer, warnings, skipped, generated_count)."""
    act_map = config["act_code_map"]
    templates = config["templates"]

    writer = PdfWriter()
    warnings = []
    skipped = []
    generated = 0

    for flight in flights:
        if station and flight["dep"] != station:
            skipped.append(
                f"{flight.get('flight_number', '?')}: departs {flight['dep']}, not "
                f"{station} -- no loading instruction needed at this station."
            )
            continue

        act = flight.get("act", "")
        template_key = act_map.get(act)
        if not template_key:
            skipped.append(
                f"{flight.get('flight_number', '?')}: unrecognized aircraft code '{act}' -- "
                f"not in act_code_map. Add a mapping to aircraft_config.json and rerun."
            )
            continue

        template_cfg = templates[template_key]
        template_path = SKILL_DIR / template_cfg["pdf"]

        local_std = compute_local_std(
            flight["date"], flight["std_utc"], flight["dep"], tz_table, warnings, flight["flight_number"]
        )
        display_flight_number = convert_flight_number(flight["flight_number"], carrier_map, warnings)
        display_date = format_date_display(flight["date"], date_format, warnings, flight["flight_number"])

        overlay_buf = build_overlay(template_cfg, flight, local_std, display_flight_number, display_date, warnings)
        overlay_reader = PdfReader(overlay_buf)
        base_reader = PdfReader(str(template_path))
        base_page = base_reader.pages[0]
        base_page.merge_page(overlay_reader.pages[0])
        writer.add_page(base_page)
        generated += 1

    return writer, warnings, skipped, generated


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flights", required=True, help="Path to flights.json")
    ap.add_argument("--output", required=True, help="Path to write the combined PDF")
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
        help="If set (e.g. BGY), only flights DEPARTING from this station get a page. "
        "Flights departing elsewhere (e.g. inbound legs) are skipped -- ground handling "
        "only needs a loading instruction for the leg they're actually loading.",
    )
    args = ap.parse_args()

    flights = load_json(args.flights)
    config = load_json(args.config)
    tz_table = load_json(args.timezones)
    tz_table = {k: v for k, v in tz_table.items() if not k.startswith("_")}
    carrier_map = load_json(args.carriers)
    carrier_map = {k: v for k, v in carrier_map.items() if not k.startswith("_")}

    writer, warnings, skipped, generated = generate_lir_pdf(
        flights, config, tz_table, carrier_map, station=args.station, date_format=args.date_format
    )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "wb") as f:
        writer.write(f)

    print(f"Generated {generated} page(s) -> {args.output}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  - {w}")
    if skipped:
        print(f"\n{len(skipped)} flight(s) SKIPPED (no page generated):")
        for s in skipped:
            print(f"  - {s}")
    if not warnings and not skipped:
        print("No warnings.")


if __name__ == "__main__":
    main()
