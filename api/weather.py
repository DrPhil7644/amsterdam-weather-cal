from http.server import BaseHTTPRequestHandler
import urllib.request
import re
import json
from datetime import datetime, timezone, timedelta

CITIES = {
    "amsterdam": {
        "name":      "Amsterdam",
        "url_base":  "https://www.weeronline.nl/Europa/Nederland/Amsterdam/4058223",
    },
    "rotterdam": {
        "name":      "Rotterdam",
        "url_base":  "https://www.weeronline.nl/Europa/Nederland/Rotterdam/4057931",
    },
    "alkmaar": {
        "name":      "Alkmaar",
        "url_base":  "https://www.weeronline.nl/Europa/Nederland/Alkmaar/4058218",
    },
}

# defaults (kept for backwards-compat with the Vercel handler)
_URL_FORECAST = CITIES["amsterdam"]["url_base"] + "/weersverwachting-14dagen"
_URL_POLLEN   = CITIES["amsterdam"]["url_base"] + "/hooikoorts"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9",
}

_POLLEN_LABEL = {0: "", 1: "Laag", 2: "Matig", 3: "Hoog", 4: "Zeer hoog", 5: "Extreem"}
_POLLEN_EMOJI = {0: "", 1: "", 2: "🌾", 3: "🤧", 4: "🤧🤧", 5: "🤧🤧🤧"}


def _fetch_next_data(url):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="replace")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    return json.loads(max(scripts, key=len))


def _fetch_forecast(city="amsterdam"):
    url = CITIES[city]["url_base"] + "/weersverwachting-14dagen"
    data = _fetch_next_data(url)
    return data["props"]["pageProps"]["forecastData"]["Fullday"]["Dorp"]


def _fetch_pollen(city="amsterdam"):
    """Return {date_str: hayfever_dict} for the next 7 days."""
    url = CITIES[city]["url_base"] + "/hooikoorts"
    data = _fetch_next_data(url)
    result = {}
    for d in data["props"]["pageProps"]["forecastData"]:
        date = d["intervalStart"]["formatted"][:10]  # YYYY-MM-DD
        result[date] = d["digits"]["health"]["hayFever"]
    return result


def _icon_emoji(code):
    c = (code or "s0000000").lower()
    cloud = int(c[2]) if len(c) > 2 and c[2].isdigit() else 0
    if "t" in c[1:]:
        return "⛈️"
    if "r" in c:
        ri = c.index("r")
        intensity = int(c[ri + 1]) if ri + 1 < len(c) and c[ri + 1].isdigit() else 1
        return "🌧️" if intensity >= 2 else "🌦️"
    if "s" in c[2:] or "h" in c[2:]:  # snow / hagel
        return "❄️"
    return ["☀️", "🌤️", "⛅", "☁️"][min(cloud, 3)]


def _escape(text):
    return (
        text.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
    )


def _fold(line):
    """RFC 5545: fold lines longer than 75 octets."""
    parts, buf = [], line
    while len(buf.encode()) > 75:
        n = 75
        while len(buf[:n].encode()) > 75:
            n -= 1
        parts.append(buf[:n])
        buf = " " + buf[n:]
    parts.append(buf)
    return "\r\n".join(parts)


def _build_ics(days, pollen=None, past_events=None, city="amsterdam"):
    pollen = pollen or {}
    city_name = CITIES[city]["name"]
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//Weeronline {city_name} 14-daagse//NL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Weer {city_name} \U0001f326️",
        f"X-WR-CALDESC:14-daagse weersverwachting voor {city_name} (weeronline.nl)",
        "X-WR-TIMEZONE:Europe/Amsterdam",
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:P1D",
    ]

    # Preserved past events (already happened — kept verbatim, re-folded)
    for block in (past_events or []):
        for prop in block.splitlines():
            if prop:
                lines.append(prop)

    for d in days:
        date_str = d["ValidDay"]  # YYYY-MM-DD
        y, mo, dy = date_str.split("-")
        dt_start = f"{y}{mo}{dy}"
        dt_end = (datetime(int(y), int(mo), int(dy)) + timedelta(days=1)).strftime("%Y%m%d")

        emoji       = _icon_emoji(d.get("WXCO_WOL", "s0000000"))
        tn          = d.get("TNTN", "?")
        tx          = d.get("TXTX", "?")
        rain        = d.get("RRRR") or 0
        rain_chance = d.get("RRRK") or 0
        wind_d      = d.get("DDDD", "")
        wind_bft    = d.get("FFFF_BFT", 0)
        uv          = d.get("UVINDEX", "")
        wxtext      = d.get("WXCO_TEXT", "")
        feels       = d.get("FEELS_LIKE", "")

        # Hayfever — available for first 7 days
        hf        = pollen.get(date_str, {})
        hf_score  = hf.get("maxTotal", 0) or 0
        hf_label  = _POLLEN_LABEL.get(hf_score, "")
        hf_emoji  = _POLLEN_EMOJI.get(hf_score, "")
        hf_msg    = re.sub(r"\[/?b\]", "", hf.get("message", ""))
        # Extract just the plant names from the message
        hf_plants = ""
        if hf_msg:
            m = re.search(r"voor:\s*(.+?)\.?\s*$", hf_msg)
            if m:
                hf_plants = m.group(1).strip()

        summary = f"{emoji} {tx}°C · {wxtext}"
        if hf_score >= 2:
            summary += f" · {hf_emoji} {hf_label}"

        desc_lines = [
            wxtext,
            "",
            f"🌡️ {tx}°C (voelt als {feels}°C)",
            f"💨 Wind: {wind_d} {wind_bft} bft",
        ]
        if rain_chance > 0:
            if rain > 0:
                desc_lines.append(f"🌧️ Neerslag: {rain:.1f}mm ({rain_chance}%)")
            else:
                desc_lines.append(f"🌦️ Neerslagkans: {rain_chance}%")
        if uv:
            desc_lines.append(f"☀️ UV-index: {uv}")
        if hf_score >= 1:
            line = f"🌾 Hooikoorts: {hf_label}"
            if hf_plants:
                line += f" — {hf_plants}"
            desc_lines.append(line)
        desc_lines.append("📍 weeronline.nl")

        description = "\n".join(desc_lines)

        lines += [
            "BEGIN:VEVENT",
            f"UID:{date_str}-{city}-weeronline@cal",
            f"DTSTART;VALUE=DATE:{dt_start}",
            f"DTEND;VALUE=DATE:{dt_end}",
            f"SUMMARY:{_escape(summary)}",
            f"DESCRIPTION:{_escape(description)}",
            "TRANSP:TRANSPARENT",
            "STATUS:CONFIRMED",
            f"DTSTAMP:{now}",
            f"LAST-MODIFIED:{now}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            days   = _fetch_forecast()
            pollen = _fetch_pollen()
            body   = _build_ics(days, pollen).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Disposition", 'inline; filename="amsterdam-weather.ics"')
            self.send_header("Cache-Control", "max-age=3600, public")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(str(exc).encode())

    def log_message(self, fmt, *args):
        pass


# ── local dev: python api/weather.py ─────────────────────────────────────────
if __name__ == "__main__":
    from http.server import HTTPServer
    print("Serving on http://localhost:8000 …")
    HTTPServer(("", 8000), handler).serve_forever()
