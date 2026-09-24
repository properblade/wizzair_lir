# wizzair_lir

A Hermes Agent / Claude Agent Skill that generates Wizz Air Loading Instruction Reports (LIR)
from a flight rotation report. Fills in route, flight number, registration, date, local STD, and
the standard cargo-hold load pattern for each flight, producing one combined PDF ready to print
for ramp staff.

This is a **skill** (machine-readable instructions + scripts), not a standalone app -- it's
meant to be installed into an agent (Hermes, Claude, or any tool following the open
[Agent Skills](https://github.com/anthropics/skills) standard) and invoked by it. See
`SKILL.md` for what the agent reads.

## Install

### Hermes Agent

```bash
git clone https://github.com/<your-org>/wizzair_lir.git ~/.hermes/skills/wizzair_lir
cd ~/.hermes/skills/wizzair_lir
pip install -r requirements.txt --break-system-packages   # add this flag only if pip requires it
```

Then inside Hermes: `/reload-skills`, and start a new session.

### Claude (claude.ai / Claude Code)

Zip this folder and upload it as a Skill, or place it under your local skills directory,
following Anthropic's [Agent Skills docs](https://docs.claude.com).

## Run it directly (no agent needed)

```bash
pip install -r requirements.txt
python3 scripts/run_lir.py --input rotation_report.pdf --output loading_instructions.pdf --station BGY
```

Needs Python 3.9+.

## What's in here

```
SKILL.md                    what the agent reads -- start here
TECHNICAL_REFERENCE.md      internals reference for maintainers (not needed for normal runs)
requirements.txt            pypdf, reportlab, pdfplumber
scripts/
  run_lir.py                 one-command pipeline: rotation-report PDF -> LIR PDF
  parse_rotation_report.py   PDF -> flights.json
  generate_lir.py            flights.json -> combined LIR PDF
  paths.py                   path resolution (plain scripts or a frozen exe)
  aircraft_config.json       template + hold coordinates + standard load pattern per type
  airport_timezones.json     airport code -> IANA timezone
  carrier_codes.json         ICAO -> IATA flight-number prefix
assets/templates/*.pdf       the four blank official Wizz LIRF forms (A320, A321 CEO/NEO/XLR)
```

## Status / known gaps

- A321 XLR has no confirmed standard load pattern yet (no XLR tail currently rotates through
  BGY) -- those hold boxes print blank rather than a guessed value.
- `aircraft_config.json`'s `act_code_map` covers the aircraft-type codes seen so far
  (`320`, `32N`, `321`, `32Q`). New codes need a one-line addition when they show up.
- `airport_timezones.json` only needs departure-airport entries, since output is filtered to a
  single station's departures (`--station BGY`).

See `TECHNICAL_REFERENCE.md` for the full design notes and assumptions.

## License

MIT -- see `LICENSE`.
