#!/usr/bin/env python3
"""Fetch weeronline forecast, merge with saved past events, write ICS."""
import sys, os, re
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from api.weather import _fetch_forecast, _fetch_pollen, _build_ics

OUT = os.path.join(os.path.dirname(__file__), "docs", "amsterdam-weather.ics")


def _read_past_events(path):
    """Return a list of unfolded VEVENT blocks for days before today."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Unfold RFC 5545 continuation lines before parsing
    content = re.sub(r"\r\n[ \t]", "", content)
    today = datetime.now().strftime("%Y%m%d")
    past = []
    for block in re.findall(r"BEGIN:VEVENT.*?END:VEVENT", content, re.DOTALL):
        m = re.search(r"DTSTART;VALUE=DATE:(\d{8})", block)
        if m and m.group(1) < today:
            past.append(block.strip())
    return past


past   = _read_past_events(OUT)
ics    = _build_ics(_fetch_forecast(), _fetch_pollen(), past_events=past)

with open(OUT, "w", encoding="utf-8") as f:
    f.write(ics)

total   = len(re.findall(r"BEGIN:VEVENT", ics))
current = total - len(past)
print(f"Written {total} events ({len(past)} past + {current} new) → {OUT}", file=sys.stderr)
