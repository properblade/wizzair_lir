---
name: wizzair_lir
description: Generates Wizz Air Loading Instruction Reports (LIRF / "loading instructions") from a flight schedule, rotation report, or any list of flights. Use this whenever the user gives you a flight list, daily schedule, or rotation report (as a PDF, pasted table, or spreadsheet) and asks for loading instructions, a loading report, LIR, LIRF, or cargo hold paperwork for those flights -- even if they just say "generate the loading instructions for today's flights" without naming the file format. Produces one pre-filled A320/A321 CEO/NEO/XLR loading form per flight (route, flight number, registration, date, local STD, and the standard cargo-hold load pattern), combined into a single PDF ready to print for ramp staff.
---

# Wizz Air Loading Instruction Report (LIR) Generator

## What this actually produces

A Wizz Air LIR template has two halves: a "LOADING INSTRUCTION" diagram (blank cargo hold
layout with max weights) and a "LOADING REPORT" diagram (the same layout, but with PCS/KGS
boxes for what actually got loaded). This skill fills in the **header fields** (route, flight
number, registration, date, local STD) and the **standard PCS load pattern** for each flight.
It does not, and should not, try to compute real cargo weights, dangerous-goods handling, or
weight-and-balance/CG figures -- those depend on the actual bags checked in for that specific
flight and belong in the airline's real load-control system, not in a static hold pattern. What
this skill automates is the paperwork prep that's identical for every flight of a given aircraft
type at this station, so ramp staff get a form that's already correctly selected and headered,
with only the true exceptions left for them to write in by hand.

## Setup (one-time, on the machine running this skill)

Needs Python 3.9+ (for the `zoneinfo` timezone module) and three packages:

```bash
pip install -r requirements.txt
```

No other setup or network access is needed after that -- everything else (templates, config)
is bundled in this skill folder.

## Overview of the workflow

1. Extract the flight list into a small JSON structure (this is the part that varies by
   input format, so do it yourself with your normal reading tools -- don't try to write a
   universal parser).
2. Run `scripts/generate_lir.py` on that JSON. It picks the right template per aircraft type,
   converts UTC STD to the departure airport's local time, applies the standard load pattern,
   and merges everything into one combined PDF.
3. Read the script's printed warnings before handing the PDF back -- they tell you exactly
   which flights need a human's attention (unknown aircraft code, unknown airport timezone, no
   load pattern configured yet) rather than silently printing something wrong.

## Step 1: Extract flights into JSON

If the input is the "Daily Flight Schedule Report" rotation-report PDF (columns `DATE FLIGHT
TYP DEP DES STD STA [ETD] [ETA] REG ACT CAP PAX CPT`, dates as `M/D/YYYY`, all times UTC),
use the bundled parser instead of extracting by hand:

```bash
python3 scripts/parse_rotation_report.py --input rotation_report.pdf --output /tmp/flights.json
```

It prints how many rows it parsed and lists any line it couldn't match as a flight row --
expected for report headers/footers, but a real flight row showing up there means the layout
changed and `FLIGHT_LINE_RE` in that script needs a small adjustment. If a different report
layout, a pasted table, or a spreadsheet is given instead, this parser won't apply -- read it
yourself and build the same JSON shape below.

For any other input format, read the flight list (PDF, pasted table, spreadsheet -- whatever
the user gave you) and build a JSON array, one object per flight, with these fields:

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

Notes on extraction:
- `date` must be ISO format (`YYYY-MM-DD`). Schedules often show dates as `M/D/YYYY` (e.g.
  Wizz's rotation report) or `D/M/YYYY` -- look at the report's own date-range header to
  disambiguate rather than guessing, since `9/7/2026` is ambiguous on its own.
- `std_utc` should be the STD exactly as shown in the source, in 24h `HH:MM`. Only pull it from
  a column explicitly labeled UTC (or confirm the report states all times are UTC, as Wizz's
  rotation report does) -- the script does the local-time conversion itself, so don't convert it
  yourself here.
- `act` is whatever aircraft-type code the source uses (e.g. `320`, `321`, `32Q`, or an ICAO code
  like `A21N`). Pass it through as-is; `aircraft_config.json` maps it to a template.
- `flight_number` should keep the source's ICAO operator prefix as-is (e.g. `WMT 3131`, `WZZ
  4351`) -- don't convert it yourself. The script automatically converts the ICAO prefix to the
  matching IATA code (`WMT`->`W4`, `WZZ`->`W6`, `WUK`->`W9`, `WAZ`->`5W`, per
  `carrier_codes.json`) before printing it on the form, since that's the convention ramp staff
  expect on the LIR.
- Every flight in the source becomes one entry, including both legs of a rotation (e.g. the
  inbound BBU-BGY and outbound BGY-BBU are two separate flights needing two separate forms).

Save this array to a JSON file (e.g. `/tmp/flights.json`).

## Step 2: Run the generator

```bash
python3 scripts/generate_lir.py --flights /tmp/flights.json --output loading_instructions.pdf --station BGY
```

The Date field is printed as `DD/MM/YYYY` by default (e.g. `08/09/2026`); pass
`--date-format` with a different strftime pattern if the user wants something else.

`--station` filters to only the flights that actually depart from that station -- ground
handling only needs a loading instruction for the leg they're physically loading, not for
inbound legs landing there. This also makes STD (LT) unambiguous: since every generated flight
departs from `--station`, the local time printed is always that station's local time, computed
by converting the schedule's UTC `std_utc` using `airport_timezones.json`. Omit `--station` only
if the user explicitly wants pages for every flight in the list regardless of departure airport.

This does the mechanical work in one deterministic pass:
- Maps each flight's `act` code to a template via `aircraft_config.json`'s `act_code_map`.
- Converts `std_utc` to the departure airport's local time using `airport_timezones.json`
  (a small station -> IANA timezone table), correctly handling the date so DST is right.
- Fills in the standard PCS load pattern for that aircraft type's `default_pattern` (currently:
  A320 -> 80 PCS in the forward hold, all others NIL; A321 CEO/NEO -> 90 PCS in the aft hold,
  all others NIL; A321 XLR has no confirmed pattern yet, so those boxes are left blank rather
  than guessed).
- Merges everything into one combined PDF, one page per flight, and writes it out.

## Step 3: Read the warnings, don't skip this

The script prints a summary after running. Two categories matter:

- **Skipped flights** (aircraft code not in `act_code_map`): no page was generated at all for
  that flight. Either the schedule used a code the table doesn't know yet, or it's a genuine data
  problem worth flagging to the user -- don't silently drop it from your response.
- **Warnings** (unknown departure-airport timezone, or no load pattern configured for that
  aircraft variant): a page WAS generated, but something on it needed a fallback -- either the
  UTC time printed instead of local time, or the PCS boxes left blank. Mention these to the user
  rather than presenting the PDF as if everything was fully auto-filled.

Both are recoverable by editing the JSON config files below and rerunning -- they're small and
meant to be extended as new routes, aircraft, or load patterns come up.

## Extending the reference data

`scripts/aircraft_config.json`:
- `act_code_map` -- add new aircraft-type codes here as new ones appear in schedules.
- `templates.*.default_pattern` -- the standard PCS-per-hold pattern for that aircraft type,
  e.g. `{"Cpt3": "90"}`. Any hold not listed gets `NIL`. Set to `null` (as XLR currently is) if
  no standard pattern has been confirmed yet -- don't invent one.
- If a flight needs a one-off pattern different from the standard (the user says something like
  "flight WZZ1234 today needs 120kg in hold 2 instead"), pass a `load_pattern` field directly
  in that flight's JSON entry instead of editing the shared config -- it overrides the default
  for that flight only.

`scripts/airport_timezones.json`:
- Add an airport code -> IANA timezone entry whenever a flight's departure airport isn't in the
  table yet. This is deliberately a manual, explicit table rather than an automatic lookup --
  guessing a station's timezone wrong and silently printing the wrong local STD on ramp paperwork
  is worse than flagging it and asking.

`scripts/carrier_codes.json`:
- Maps each Wizz AOC's ICAO code (as seen in the schedule's flight-number prefix) to the IATA
  code that should be printed on the form instead. Add a new entry if a new Wizz AOC/operator
  code ever appears. If a flight number's prefix isn't in this table, the script leaves it
  unconverted and adds a warning rather than guessing.

## If a genuinely new aircraft variant shows up

The four bundled templates (`assets/templates/a320.pdf`, `a321_ceo.pdf`, `a321_neo.pdf`,
`a321_xlr.pdf`) are Wizz Air's actual LIRF forms. If a new template revision or a new aircraft
type is introduced, add the PDF to `assets/templates/`, then add a matching entry to
`aircraft_config.json` with its own `header_boxes`, `hold_order`, `hold_boxes`, and
`first_to_load`. Coordinates are `[x0, x1, top, bottom]` in PDF points measured from the page's
top-left corner (the same convention `pdfplumber` uses) -- the easiest way to find them for a new
template is to open it with `pdfplumber`, call `page.extract_words()` and `page.rects` on it, and
match the label text and grey input-box rectangles to their coordinates, the same way the
existing four were derived.
