from http.server import BaseHTTPRequestHandler
import urllib.request
import re
import json
from datetime import datetime, timezone, timedelta

_URL = (
    "https://www.weeronline.nl/Europa/Nederland/Amsterdam/"
    "4058223/weersverwachting-14dagen"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9",
}


def _fetch_forecast():
    req = urllib.request.Request(_URL, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="replace")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    payload = max(scripts, key=len)
    data = json.loads(payload)
    return data["props"]["pageProps"]["forecastData"]["Fullday"]["Dorp"]


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


def _build_ics(days):
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Weeronline Amsterdam 14-daagse//NL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Weer Amsterdam \U0001f326️",
        "X-WR-CALDESC:14-daagse weersverwachting voor Amsterdam (weeronline.nl)",
        "X-WR-TIMEZONE:Europe/Amsterdam",
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:P1D",
    ]

    for d in days:
        date_str = d["ValidDay"]  # YYYY-MM-DD
        y, mo, dy = date_str.split("-")
        dt_start = f"{y}{mo}{dy}"
        dt_end = (datetime(int(y), int(mo), int(dy)) + timedelta(days=1)).strftime("%Y%m%d")

        emoji   = _icon_emoji(d.get("WXCO_WOL", "s0000000"))
        tn      = d.get("TNTN", "?")
        tx      = d.get("TXTX", "?")
        rain    = d.get("RRRR") or 0
        wind_d  = d.get("DDDD", "")
        wind_k  = d.get("FFFF_KM", 0)
        uv      = d.get("UVINDEX", "")
        wxtext  = d.get("WXCO_TEXT", "")
        hum     = d.get("RHRH", "")
        feels   = d.get("FEELS_LIKE", "")

        summary = f"{emoji} {tn}–{tx}°C · {wxtext}"

        desc_lines = [
            wxtext,
            f"🌡️ {tn}°C – {tx}°C  (voelt als {feels}°C)",
            f"💨 Wind: {wind_d} {wind_k} km/h",
        ]
        if rain > 0:
            desc_lines.append(f"🌧️ Neerslag: {rain:.1f} mm")
        if uv:
            desc_lines.append(f"☀️ UV-index: {uv}")
        if hum:
            desc_lines.append(f"💧 Luchtvochtigheid: {hum}%")
        desc_lines.append("📍 Bron: weeronline.nl")

        description = "\\n".join(desc_lines)

        lines += [
            "BEGIN:VEVENT",
            f"UID:{date_str}-amsterdam-weeronline@cal",
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
            days = _fetch_forecast()
            body = _build_ics(days).encode("utf-8")
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
