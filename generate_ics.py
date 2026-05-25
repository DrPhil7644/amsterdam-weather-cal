#!/usr/bin/env python3
"""Generate amsterdam-weather.ics from weeronline.nl and write to docs/."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from api.weather import _fetch_forecast, _fetch_pollen, _build_ics

out = os.path.join(os.path.dirname(__file__), "docs", "amsterdam-weather.ics")
ics = _build_ics(_fetch_forecast(), _fetch_pollen())

with open(out, "w", encoding="utf-8") as f:
    f.write(ics)

print(f"Written {len(ics.splitlines())} lines → {out}", file=sys.stderr)
