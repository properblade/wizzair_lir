---
name: wizzair_lir
description: Generates Wizz Air Loading Instruction Reports (LIR) from a flight schedule, rotation report, or any list of flights. Use whenever asked for loading instructions, a loading report, LIR, LIRF, or cargo hold paperwork for Wizz Air flights -- even if the file format isn't named. Produces one pre-filled A320/A321 CEO/NEO/XLR loading form per flight, combined into a single PDF ready to print for ramp staff.
version: 1.1.0
author: BGY Ground Handling
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [wizzair, lir, loading-instruction, aviation, pdf-generation, bgy]
    home_channels: [telegram]
prerequisites:
  commands: [python3, pip]
  packages: [pypdf, reportlab, pdfplumber]
---

# Wizz Air Loading Instruction Report (LIR) Generator

## Read this first: how to execute this skill

**This whole task is ONE shell command.** For the common case (input is a rotation-report
PDF), run exactly this and nothing else:

```bash
python3 scripts/run_lir.py --input <rotation_report.pdf> --output <output.pdf> --station BGY
```

That single command parses the PDF, converts timezones and carrier codes, applies the standard
load pattern, and writes the combined PDF. It prints a summary when done.

To keep this skill fast and reliable, especially on constrained hardware:

- **Do not read the input PDF yourself** (no vision, no manual text extraction) -- the bundled
  parser does that deterministically, faster and more accurately than reading it turn-by-turn.
- **Do not hand-build `flights.json` field by field across multiple tool calls** -- that's only
  for input formats the parser can't handle (see "Other input formats" below). Even then, build
  it in one write, not one flight at a time.
- **Do not split this into many small steps.** One command in, one PDF out. If something needs
  fixing (new airport, new aircraft code), that's a one-line edit to a JSON config file, not a
  reason to re-derive the whole pipeline.
- **Do not rewrite or "improve" this file, the scripts, or the JSON configs.** If something
  seems wrong or incomplete, say so and ask, rather than regenerating your own version. A
  rewritten copy silently drifts from what's actually tested (wrong paths, wrong data) -- this
  has happened before and cost hours to debug.
- **`TECHNICAL_REFERENCE.md` is for human maintainers, not for you to read during a normal
  run.** Only open it if you're specifically asked to debug or extend the underlying logic.

## Sending the output file on a messaging platform (Telegram, Discord, etc.)

Your final reply MUST include the literal tag `MEDIA:<absolute path to the output PDF>` on its
own line -- e.g. `MEDIA:/home/pi/output.pdf`. This is not optional and not just a mention of the
path in prose: the gateway only delivers a native file attachment when it finds this exact
`MEDIA:` tag in the reply text. Use the real absolute path you passed to `--output`.

## What this skill produces

A Wizz Air LIR template has two halves: a "LOADING INSTRUCTION" diagram (blank cargo hold
layout with max weights) and a "LOADING REPORT" diagram (same layout, with PCS/KGS boxes for
what actually got loaded). This skill fills in the **header fields** (route, flight number,
registration, date, local STD) and the **standard PCS load pattern** in the LOADING INSTRUCTION
diagram for each flight.

It does **not** compute real cargo weights, dangerous-goods handling, or weight-and-balance/CG
figures -- those depend on the actual bags checked in for that specific flight and belong in the
airline's real load-control system, not in a static hold pattern. This skill automates the
paperwork prep that's identical for every flight of a given aircraft type at this station, so
ramp staff get a form that's already correctly selected and headered, with only the true
exceptions left for them to write in by hand.

## Setup (one-time)

Needs Python 3.9+ (for `zoneinfo`) and three packages:

```bash
pip install -r requirements.txt
```

No other setup or network access is needed afterward -- templates and config are bundled here.

## Other input formats

If the input is NOT the "Daily Flight Schedule Report" PDF layout (columns `DATE FLIGHT TYP DEP
DES STD STA [ETD] [ETA] REG ACT CAP PAX CPT`, dates `M/D/YYYY`, times UTC) -- e.g. a pasted
table or a different export -- `scripts/parse_rotation_report.py` won't apply. In that case,
read the flight list and build a JSON array yourself, one write, one object per flight:

```json
{
  "date": "2026-09-07",
  "flight_number": "WMT 3131",
  "dep": "BBU",
  "des": "BGY",
  "std_utc": "02:30",
  "reg": "HA-LXM",
  "act": "321"
}
```

Then run `scripts/generate_lir.py --flights flights.json --output output.pdf --station BGY`
(the same generation step `run_lir.py` calls internally). Field notes:

- `date`: ISO `YYYY-MM-DD`. Disambiguate `M/D` vs `D/M` from the report's own date-range header
  rather than guessing.
- `std_utc`: `HH:MM`, only from a column explicitly labeled UTC. The script does the local-time
  conversion -- don't convert it yourself.
- `act`: whatever aircraft-type code the source uses (`320`, `321`, `32Q`, or ICAO like `A21N`).
  Pass through as-is; `aircraft_config.json` maps it to a template.
- `flight_number`: keep the ICAO operator prefix as-is (e.g. `WMT 3131`) -- the script converts
  it to IATA (`W4 3131`) automatically.
- Both legs of a rotation (e.g. BBU-BGY and BGY-BBU) are two separate entries.

## Reading the output: warnings and skipped flights

The script prints a summary. Two categories matter and should be relayed to whoever asked for
the PDF, not silently dropped:

- **Skipped flights** -- no page generated (unrecognized aircraft code, or doesn't depart the
  `--station` filter). Either the schedule used a new code, or a genuine data issue.
- **Warnings** -- a page WAS generated but something needed a fallback (unknown departure
  timezone -> raw UTC printed instead of local time; no load pattern for that aircraft type ->
  hold boxes left blank).

Both are fixed by editing the JSON config files below and rerunning.

## Extending the reference data

`scripts/aircraft_config.json`:
- `act_code_map` -- add new aircraft-type codes as they appear.
- `templates.*.default_pattern` -- the standard PCS-per-hold pattern per aircraft type, e.g.
  `{"Cpt3": "90"}`. Unlisted holds print `NIL`. Use `null` if no pattern is confirmed yet --
  don't invent one.
- A one-off pattern for a single flight (not a permanent change): pass `load_pattern` directly
  in that flight's JSON entry -- overrides the default for that flight only.

`scripts/airport_timezones.json`: airport code -> IANA timezone, for departure airports only.
Deliberately manual/explicit -- an unmapped airport falls back to raw UTC with a warning rather
than a guessed timezone.

`scripts/carrier_codes.json`: ICAO operator code -> IATA code for the printed flight number.

## Adding a new aircraft variant / template revision

1. Add the PDF to `assets/templates/`.
2. Add an entry to `aircraft_config.json` with `header_boxes`, `hold_order`,
   `instruction_hold_boxes`, and `first_to_load`. Coordinates are `[x0, x1, top, bottom]` in PDF
   points from the page's top-left (pdfplumber convention). Find them by opening the new PDF
   with `pdfplumber`, calling `page.extract_words()` and inspecting `page.rects` for label text
   and grey input-box rectangles.
3. Add the code -> template mapping to `act_code_map`.

See `TECHNICAL_REFERENCE.md` for the full internals (function-by-function reference, path
resolution details, design assumptions) if you're doing deeper maintenance work.
