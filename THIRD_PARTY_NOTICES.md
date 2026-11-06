# Third-party notices

This project uses the following third-party components. The list is
incomplete for transitive dependencies; `pip`/`pip-licenses` remains the
source of truth for the full environment.

## Garmin wellness FIT decoder

- Project: `anup-shesh/garmin-local-mcp`
- License: MIT
- Use: adapted wellness-FIT message decoding logic for sleep, HRV, RHR,
  skin temperature, naps, and sleep score.
- Copyright (c) 2026 Anup Shesh. The adapted code lives in
  `services/garmin/fit_wellness.py` and retains this notice.

### MIT License text

Copyright (c) 2026 Anup Shesh

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## fitparse

- Project: `dtcooper/python-fitparse`
- License: MIT
- Use: parsing FIT files without the proprietary Garmin FIT SDK.

## ReportLab

- Project: `reportlab`
- License: BSD-style
- Use: PDF generation with Platypus, Unicode fonts, tables, and page
  templates.

## Matplotlib

- Project: `matplotlib`
- License: PSF-based (Matplotlib license)
- Use: deterministic charts rendered through the `Agg` backend to PNG.

## jsonschema

- Project: `python-jsonschema/jsonschema`
- License: MIT
- Use: validating local LLM JSON contracts and plan payloads.

## python-garminconnect (optional, P8)

- Project: `cyberjunky/python-garminconnect`
- License: MIT
- Use: optional online synchronization. It is not installed or enabled by
  default; official Garmin exports are the primary data path.

## Excluded licenses

The project does not copy code from GPL-2.0 (`tcgoetz/GarminDB`) or
AGPL-3.0 (`nrvim/garmin-givemydata`) projects. The proprietary
`garmin-fit-sdk` is not used.
