# Wizz Air LIR Generator — Technical Reference

This documents how the scripts actually work, for maintenance and handoff. For a plain
getting-started guide, see `README.md` instead.

## What this system does

Turns a Wizz Air BGY rotation report (a flight schedule PDF) into a combined PDF of Loading
Instruction Reports (LIR) — one page per BGY-departing flight, with the header fields and the
standard cargo-hold load pattern pre-filled. It does **not** compute real weight & balance, CG,
or dangerous-goods data; it only automates the paperwork that's identical for every flight of a
given aircraft type at this station. See "Design decisions and assumptions" below for why.

## Pipeline overview

```
Rotation report PDF
        |
        v
parse_rotation_report.py   (regex-parses the schedule table)
        |
        v
   flights.json             (plain list of flight dicts)
        |
        v
generate_lir.py             (fills templates, converts timezones/carrier codes)
        |
        v
Combined LIR PDF
```

`run_lir.py` and `generate_lir_launcher.py` are just different front doors onto this same
pipeline — see "Entry points" below for which one to use when.

## File structure

```
scripts/
  paths.py                   path resolution (see "Frozen-exe path resolution" below)
  parse_rotation_report.py   PDF -> flights.json
  generate_lir.py            flights.json -> combined PDF
  run_lir.py                 CLI: chains the two above
  aircraft_config.json       template/hold coordinates + standard load pattern per aircraft type
  airport_timezones.json     airport code -> IANA timezone
  carrier_codes.json         ICAO -> IATA flight-number prefix
generate_lir_launcher.py     interactive entry point compiled into Generate_LIR.exe
assets/templates/*.pdf       the four blank official Wizz LIRF forms
build_exe.bat                one-time PyInstaller build script (Windows)
Generate_LIR.bat / .command / .sh   double-click launchers (need Python)
```

## Script-by-script reference

### `scripts/parse_rotation_report.py`

Regex-parses the "Daily Flight Schedule Report for `<station>` airport" PDF export.

- `FLIGHT_LINE_RE` — the one regex that matches a flight row. Columns matched, in order:
  `DATE  ICAO NUM  TYP  DEP  DES  STD  STA  [ETD]  [ETA]  REG  ACT  CAP  PAX  CPT(rest of line)`.
  `ETD`/`ETA` are optional and discarded — only the scheduled `STD` is used, never the actual
  departure/arrival time, since the LIR's "STD (LT)" field means *scheduled*.
- `SKIP_PREFIXES` — line prefixes that are report headers/footers, not flight rows, and are
  silently skipped rather than reported as unmatched.
- `iso_date(date_str)` — converts the report's `M/D/YYYY` date format to ISO `YYYY-MM-DD`.
  **This assumes month-first dates**, confirmed by the report's own date-range header (e.g. a
  header of `(9/8/2026 - 9/9/2026)` only makes sense as Sep 8 -> Sep 9, not Aug 9 -> Sep 9). If a
  future report ever uses day-first dates, this function needs updating.
- `parse_pdf(path)` — the main entry, returns `(flights, unmatched)`. `unmatched` is every line
  that wasn't a recognized flight row and wasn't a known header/footer — this is the safety net:
  if a real flight row fails to match (report layout changed), it shows up here instead of being
  silently dropped.
- Each flight dict has exactly the fields `generate_lir.py` expects: `date`, `flight_number`,
  `dep`, `des`, `std_utc`, `reg`, `act`. No conversion (timezone, carrier code, aircraft mapping)
  happens here — that's all `generate_lir.py`'s job, keeping parsing and generation independent.

### `scripts/generate_lir.py`

The actual PDF generation. Key functions:

- `box_to_reportlab(box, page_height)` — converts a `[x0, x1, top, bottom]` box (pdfplumber
  convention, origin top-left) into reportlab's bottom-left-origin coordinates.
- `draw_centered(c, box, page_height, text, ...)` — draws text horizontally and vertically
  centered inside a box. Used for every field on the form.
- `compute_local_std(date_str, std_utc, dep_code, tz_table, warnings, flight_number)` — converts
  the schedule's UTC `std_utc` to the departure airport's local time, using the date (not just
  the time) so DST transitions are handled correctly via `zoneinfo`. If `dep_code` isn't in
  `tz_table`, it falls back to printing the raw UTC value with a `Z` suffix and appends a
  warning — it never guesses a timezone.
- `convert_flight_number(flight_number, carrier_map, warnings)` — swaps the ICAO operator prefix
  (`WMT`, `WZZ`, ...) for the IATA code Wizz actually prints on ramp paperwork (`W4`, `W6`, ...).
  Unrecognized prefixes are left as-is, with a warning.
- `format_date_display(date_iso, fmt, warnings, flight_number)` — reformats the ISO date for
  display using a `strftime` format string (default `%d/%m/%Y`).
- `build_overlay(template_cfg, flight, local_std, display_flight_number, display_date, warnings)`
  — builds one page's worth of overlay text (header fields + hold values) as an in-memory PDF,
  using `reportlab`.
- `generate_lir_pdf(flights, config, tz_table, carrier_map, station=None, date_format=...)` — the
  core, reusable function. Loops over flights, resolves each to a template via
  `aircraft_config.json`'s `act_code_map`, merges the overlay onto the matching blank template
  page with `pypdf`, and collects everything into one `PdfWriter`. Returns
  `(writer, warnings, skipped, generated_count)`. This is what `run_lir.py` and
  `generate_lir_launcher.py` both call directly (no subprocess) — `main()` in this file is just
  the CLI wrapper around it.
- **Where values land on the page:** standard load-pattern values go in the top "LOADING
  INSTRUCTION" diagram's single box per hold (`instruction_hold_boxes` in the config) — this is
  what tells ramp staff what to load. The bottom "LOADING REPORT" diagram's separate PCS/KGS
  boxes are deliberately never touched by this script; they stay blank for staff to fill in by
  hand after loading, confirming what actually went on.

### `scripts/run_lir.py`

Thin CLI that chains `parse_rotation_report.parse_pdf()` and `generate_lir.generate_lir_pdf()`
into one command, printing the parse summary and the generation summary together. Optionally
saves the intermediate `flights.json` with `--save-json` for inspection.

### `generate_lir_launcher.py`

Same pipeline again, but interactive (prompts for the PDF path and station instead of taking
CLI flags) and with print statements aimed at a non-technical user watching a console window.
This is the file `build_exe.bat` compiles into `Generate_LIR.exe`. Output is always written next
to the exe/script itself (not next to the input PDF), specifically to avoid failures when the
input PDF sits in a read-only or permission-restricted folder.

### `scripts/paths.py`

One function, `get_base_dir()`, used by every other script to find `scripts/*.json` and
`assets/templates/*.pdf` reliably. See "Frozen-exe path resolution" below for why this exists.

## Config file schemas

### `aircraft_config.json`

```
act_code_map:   { "<schedule's ACT code>": "<template key>" }
templates:
  <template key>:
    label:                   display name, used in warning messages
    pdf:                     path to the blank template, relative to the package root
    page_size:                [width, height] in PDF points
    header_boxes:             { field_name: [x0, x1, top, bottom] } for Route/Flight
                               number/Registration/Date/STD boxes
    hold_order:                list of hold names, left-to-right as they appear on the form
    instruction_hold_boxes:    { hold_name: [x0, x1, top, bottom] } -- the TOP diagram's boxes
    first_to_load:             which hold is marked "first to load" on the template (informational)
    default_pattern:           { hold_name: "PCS value" } or null if none confirmed yet.
                                Holds in hold_order but not in default_pattern print as "NIL".
```
All box coordinates are `[x0, x1, top, bottom]` in PDF points, measured from the page's
top-left corner (pdfplumber's convention) — `generate_lir.py` converts them internally.

### `airport_timezones.json`

Flat `{ "<3-letter airport code>": "<IANA timezone name>" }`. Only departure-airport codes
matter for `compute_local_std` — destination airport timezones are never looked up.

### `carrier_codes.json`

Flat `{ "<ICAO operator code>": "<IATA code>" }`.

## Frozen-exe path resolution

`generate_lir.py` and `run_lir.py` both need to find `scripts/*.json` and
`assets/templates/*.pdf` regardless of whether they're running as plain `.py` files or bundled
inside `Generate_LIR.exe` by PyInstaller. Plain `__file__`-based resolution breaks under
PyInstaller, because `__file__` points into a temporary extraction folder, not where the actual
exe (and the external data files sitting next to it) live.

`paths.get_base_dir()` handles both cases:
- Frozen (`sys.frozen` set by PyInstaller): base dir = the folder containing the `.exe` itself
  (`Path(sys.executable).parent`).
- Not frozen: base dir = the package root (two levels up from `paths.py`, since it lives in
  `scripts/`).

The JSON configs and PDF templates are deliberately **not** embedded inside the compiled exe —
only the Python code is. This keeps them editable (new airport, new aircraft code, a revised
load pattern) without ever needing to rebuild the exe.

## Design decisions and assumptions worth knowing about

- **This tool never computes real weight & balance / CG.** The `default_pattern` values are a
  station's standard baggage-loading assumption for a given aircraft type, not a measurement.
  Anything beyond that belongs in the real load-control system.
- **STD (LT) uses the *departure* airport's local time**, not the destination's. Filtering to
  `--station BGY` makes this unambiguous for BGY ground handling, since every generated flight
  then departs BGY by definition.
- **Unrecognized data never gets guessed** — an unknown aircraft code skips the flight entirely
  (no page), an unknown departure timezone falls back to raw UTC with a `Z` suffix, an unknown
  ICAO carrier prefix prints as-is, and a missing `default_pattern` (currently: A321 XLR) leaves
  the hold boxes blank. All four cases show up in the printed warnings/skipped list — nothing is
  silently wrong on a page without the user having full ability to notice it.
- **The `32N` aircraft code** (first seen 14 Sep 2026, WMT 3551/3552, TSR route) was mapped to
  the `A320` template based on matching seat capacity (186) with other confirmed A320 flights in
  the same report, not from a confirmed source. Worth double-checking against real ops data.
- **Two rows per rotation.** A rotation report lists inbound and outbound legs as separate rows
  (e.g. BBU→BGY and BGY→BBU); `parse_rotation_report.py` treats them as two independent flights,
  and `--station BGY` filters to only the outbound (BGY-departing) leg, since that's the one
  ground handling at BGY actually needs paperwork for.

## Extending this system

- **New airport for the timezone table:** add `"<code>": "<IANA timezone>"` to
  `airport_timezones.json`. Only needed for airports that appear as a *departure*.
- **New aircraft-type code:** add `"<code>": "<template key>"` to `aircraft_config.json`'s
  `act_code_map`.
- **New or changed standard load pattern:** edit that aircraft type's `default_pattern` in
  `aircraft_config.json`.
- **New Wizz operator/AOC code:** add `"<ICAO>": "<IATA>"` to `carrier_codes.json`.
- **A one-off load pattern for a single flight** (not a permanent change): pass a `load_pattern`
  field directly in that flight's `flights.json` entry — it overrides the aircraft type's
  `default_pattern` for that flight only, without touching the shared config.
- **A genuinely new template revision or aircraft variant:** add the PDF to
  `assets/templates/`, then add a matching entry to `aircraft_config.json` with its own
  `header_boxes`, `hold_order`, `instruction_hold_boxes`, and `first_to_load`. Find the
  coordinates by opening the new PDF with `pdfplumber`, calling `page.extract_words()` and
  inspecting `page.rects` for the label text and the grey input-box rectangles, matching them to
  their coordinates the same way the existing four templates were derived.
- **Report layout changes** (new/renamed columns, different date format): update
  `FLIGHT_LINE_RE` and/or `iso_date()` in `parse_rotation_report.py`. Re-run against a sample
  report and check the `unmatched` list is empty (aside from expected header/footer lines).
