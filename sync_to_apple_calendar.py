#!/usr/bin/env python3
"""Push weather events directly into Apple Calendar via osascript.
   No subscriptions — events are written straight to the calendar,
   which then syncs to iPhone via iCloud automatically."""

import sys, os, re, subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from api.weather import (CITIES, _fetch_forecast, _fetch_pollen,
                         _icon_emoji, _POLLEN_LABEL, _POLLEN_EMOJI)

MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


def _build_events(days, pollen):
    today = datetime.now().strftime("%Y-%m-%d")
    events = []
    for d in days:
        date_str = d["ValidDay"]
        if date_str < today:
            continue  # past days stay as-is in Calendar

        emoji      = _icon_emoji(d.get("WXCO_WOL", "s0000000"))
        tx         = d.get("TXTX", "?")
        rain       = d.get("RRRR") or 0
        rain_chance= d.get("RRRK") or 0
        wind_d     = d.get("DDDD", "")
        wind_bft   = d.get("FFFF_BFT", 0)
        uv         = d.get("UVINDEX", "")
        wxtext     = d.get("WXCO_TEXT", "")
        feels      = d.get("FEELS_LIKE", "")

        hf       = pollen.get(date_str, {})
        hf_score = hf.get("maxTotal", 0) or 0
        hf_label = _POLLEN_LABEL.get(hf_score, "")
        hf_emoji = _POLLEN_EMOJI.get(hf_score, "")
        hf_msg   = re.sub(r"\[/?b\]", "", hf.get("message", ""))
        hf_plants = ""
        if hf_msg:
            m = re.search(r"voor:\s*(.+?)\.?\s*$", hf_msg)
            if m:
                hf_plants = m.group(1).strip()

        summary = f"{emoji} {tx}°C · {wxtext}"
        if hf_score >= 2:
            summary += f" · {hf_emoji} {hf_label}"

        desc_lines = [
            wxtext, "",
            f"🌡️ {tx}°C (voelt als {feels}°C)",
            f"💨 Wind: {wind_d} {wind_bft} bft",
        ]
        if rain_chance > 0:
            desc_lines.append(f"🌧️ Neerslag: {rain:.1f}mm ({rain_chance}%)"
                              if rain > 0 else f"🌦️ Neerslagkans: {rain_chance}%")
        if uv:
            desc_lines.append(f"☀️ UV-index: {uv}")
        if hf_score >= 1:
            hf_line = f"🌾 Hooikoorts: {hf_label}"
            if hf_plants:
                hf_line += f" — {hf_plants}"
            desc_lines.append(hf_line)
        desc_lines.append("📍 weeronline.nl")

        events.append({
            "date":        date_str,
            "summary":     summary,
            # Use | as line separator — replaced with return in AppleScript
            "description": "|".join(desc_lines),
        })
    return events


def _as_escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _sync_city(city_name, events):
    cal_name = f"Weer {city_name}"

    event_blocks = []
    for ev in events:
        y, mo, dy = ev["date"].split("-")
        as_date = f"{MONTH_NAMES[int(mo)]} {int(dy)}, {y}"
        summary = _as_escape(ev["summary"])
        description = _as_escape(ev["description"])

        event_blocks.append(f"""
    set eDate to date "{as_date}"
    set rawDesc to "{description}"
    set AppleScript's text item delimiters to "|"
    set descParts to text items of rawDesc
    set AppleScript's text item delimiters to return
    set formattedDesc to descParts as text
    set AppleScript's text item delimiters to ""
    make new event at end of events of targetCal with properties {{summary:"{summary}", start date:eDate, end date:eDate, allday event:true, description:formattedDesc}}""")

    script = f"""
tell application "Calendar"
    if not (exists (first calendar whose name is "{cal_name}")) then
        make new calendar with properties {{name:"{cal_name}"}}
    end if
    set targetCal to first calendar whose name is "{cal_name}"

    set todayStart to current date
    set hours of todayStart to 0
    set minutes of todayStart to 0
    set seconds of todayStart to 0

    set keepGoing to true
    repeat while keepGoing
        try
            set e to first event of targetCal whose start date >= todayStart
            delete e
        on error
            set keepGoing to false
        end try
    end repeat
{"".join(event_blocks)}
end tell
"""
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())


for city, config in CITIES.items():
    try:
        days   = _fetch_forecast(city)
        pollen = _fetch_pollen(city)
        events = _build_events(days, pollen)
        _sync_city(config["name"], events)
        print(f"✓ {config['name']}: {len(events)} events → Apple Calendar", file=sys.stderr)
    except Exception as e:
        print(f"✗ {config['name']}: {e}", file=sys.stderr)
