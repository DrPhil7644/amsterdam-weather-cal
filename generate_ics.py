#!/usr/bin/env python3
"""Fetch weeronline forecasts for all cities, merge with past events, write ICS files."""
import sys, os, re
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from api.weather import CITIES, _fetch_forecast, _fetch_pollen, _build_ics

DOCS = os.path.join(os.path.dirname(__file__), "docs")


def _read_past_events(path):
    """Return a list of unfolded VEVENT blocks for days before today."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r"\r\n[ \t]", "", content)
    today = datetime.now().strftime("%Y%m%d")
    past = []
    for block in re.findall(r"BEGIN:VEVENT.*?END:VEVENT", content, re.DOTALL):
        m = re.search(r"DTSTART;VALUE=DATE:(\d{8})", block)
        if m and m.group(1) < today:
            past.append(block.strip())
    return past


for city in CITIES:
    out = os.path.join(DOCS, f"{city}-weather.ics")
    past   = _read_past_events(out)
    ics    = _build_ics(_fetch_forecast(city), _fetch_pollen(city),
                        past_events=past, city=city)

    with open(out, "w", encoding="utf-8") as f:
        f.write(ics)

    total   = len(re.findall(r"BEGIN:VEVENT", ics))
    current = total - len(past)
    print(f"{city}: {total} events ({len(past)} past + {current} new) → {out}",
          file=sys.stderr)
