"""
Wiesel Wetter Crawler
Nutzt wttr.in (kostenlos, kein API Key) für Erlangen und Nürnberg.
Täglich um 20:00 ausführen – schreibt knowledge_base/wetter-heute.md

Logik:
- Heute      → kurz (Crawler läuft abends, Tag fast vorbei)
- Morgen     → ausführlich mit Stundentabelle (Vorlesungszeiten)
- Übermorgen → kurz
"""

import urllib.request
import json
from datetime import datetime, date, timedelta
from pathlib import Path

CITIES = {
    "Erlangen": "https://wttr.in/49.5897,11.0039?format=j1&lang=de",
    "Nürnberg": "https://wttr.in/49.4521,11.0767?format=j1&lang=de",
}
OUTPUT = Path(__file__).parent.parent / "knowledge_base" / "wetter-heute.md"


def fetch_weather(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WieselBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  Fehler beim Abrufen: {e}")
        return None


def get_schirm_empfehlung(regen_mm: float, regen_chance: int) -> str:
    if regen_chance >= 60 or regen_mm >= 2.0:
        return "🌂 **Schirm mitnehmen!** Regen wahrscheinlich."
    elif regen_chance >= 30 or regen_mm >= 0.5:
        return "🌂 Vielleicht Schirm einpacken, sicher ist sicher."
    return "☀️ Kein Schirm nötig."


def get_temp_tipp(temp_max: int, temp_min: int) -> str:
    if temp_max >= 28:
        return "🥵 Heute wird's heiß — Wasser nicht vergessen."
    elif temp_max >= 22:
        return "😎 Angenehm warm, leichte Kleidung reicht."
    elif temp_max >= 15:
        return "🧥 Leichte Jacke empfohlen."
    elif temp_max >= 8:
        return "🧣 Heute lieber warm anziehen."
    else:
        return "🥶 Richtig kalt — Winterjacke, Mütze, Schal."


def get_wind_tipp(wind_kmh: int) -> str:
    if wind_kmh >= 50:
        return "💨 Starker Wind — Schirm könnte sich umdrehen!"
    elif wind_kmh >= 30:
        return "💨 Windig heute."
    return ""


def wetter_beschreibung(code: int) -> str:
    codes = {
        113: "☀️ Sonnig", 116: "⛅ Teilweise bewölkt", 119: "☁️ Bewölkt",
        122: "☁️ Bedeckt", 143: "🌫️ Neblig", 176: "🌦️ Regenschauer",
        200: "⛈️ Gewitter", 263: "🌦️ Nieselregen", 266: "🌧️ Nieselregen",
        293: "🌦️ Leichter Regen", 296: "🌧️ Regen", 302: "🌧️ Starker Regen",
        305: "🌧️ Starker Regenschauer", 317: "🌨️ Schneeregen",
        323: "🌨️ Leichter Schneefall", 326: "❄️ Schneefall",
        332: "❄️ Starker Schneefall", 353: "🌦️ Leichter Regenschauer",
        356: "🌧️ Starker Regenschauer", 368: "🌨️ Leichter Schneeschauer",
        386: "⛈️ Gewitter mit Regen", 389: "⛈️ Starkes Gewitter",
    }
    return codes.get(code, "🌡️ Wechselhaft")


def parse_hourly(weather_day: dict) -> list[dict]:
    """Stündliche Vorhersage für Vorlesungszeiten (8–18 Uhr)."""
    relevant = {"800", "1000", "1200", "1400", "1600", "1800"}
    result = []
    for h in weather_day.get("hourly", []):
        t = h.get("time", "")
        if t not in relevant:
            continue
        result.append({
            "uhrzeit": t.zfill(4)[:2] + ":" + t.zfill(4)[2:],
            "temp":         int(h.get("tempC", 0)),
            "regen_chance": int(h.get("chanceofrain", 0)),
            "wind":         int(h.get("windspeedKmph", 0)),
            "code":         int(h.get("weatherCode", 113)),
            "regen_mm":     float(h.get("precipMM", 0)),
        })
    return result


def day_stats(day: dict) -> dict:
    hourly = day.get("hourly", [{}])
    regen_mm = sum(float(h.get("precipMM", 0)) for h in hourly)
    return {
        "t_max":        int(day["maxtempC"]),
        "t_min":        int(day["mintempC"]),
        "regen_chance": max(int(h.get("chanceofrain", 0)) for h in hourly),
        "regen_mm":     regen_mm,
        "wind":         int(sum(int(h.get("windspeedKmph", 0)) for h in hourly) / max(len(hourly), 1)),
    }


def day_kurz(day: dict, label: str) -> list[str]:
    """Kompakte Zeile — für heute (fast vorbei) und übermorgen."""
    s = day_stats(day)
    schirm = get_schirm_empfehlung(s["regen_mm"], s["regen_chance"])
    wind_tipp = get_wind_tipp(s["wind"])
    lines = [
        f"### {label}",
        "",
        f"- 🌡️ {s['t_min']}°C – {s['t_max']}°C · 🌧️ max. {s['regen_chance']}% · 💨 Ø {s['wind']} km/h",
        f"- {schirm}",
    ]
    if wind_tipp:
        lines.append(f"- {wind_tipp}")
    lines.append("")
    return lines


def day_ausfuehrlich(day: dict, label: str) -> list[str]:
    """Ausführlich mit Stundentabelle — für morgen."""
    s = day_stats(day)
    schirm   = get_schirm_empfehlung(s["regen_mm"], s["regen_chance"])
    temp_tipp = get_temp_tipp(s["t_max"], s["t_min"])
    wind_tipp = get_wind_tipp(s["wind"])
    hourly = parse_hourly(day)

    lines = [
        f"### {label}",
        "",
        f"- 🌡️ {s['t_min']}°C – {s['t_max']}°C · 🌧️ max. {s['regen_chance']}% · 💨 Ø {s['wind']} km/h",
        f"- {schirm}",
        f"- {temp_tipp}",
    ]
    if wind_tipp:
        lines.append(f"- {wind_tipp}")

    if hourly:
        lines += [
            "",
            "| Uhrzeit | Temp | Wetter | Regen |",
            "|---------|------|--------|-------|",
        ]
        for h in hourly:
            beschr = wetter_beschreibung(h["code"])
            regen_str = f"{h['regen_chance']}%" if h["regen_chance"] > 0 else "–"
            lines.append(f"| {h['uhrzeit']} Uhr | {h['temp']}°C | {beschr} | {regen_str} |")

    lines.append("")
    return lines


def build_markdown(data: dict, city: str = "Erlangen") -> str:
    weather = data.get("weather", [])
    today     = date.today()
    tomorrow  = today + timedelta(days=1)
    overmorrow = today + timedelta(days=2)

    lines = [f"## 📍 {city}", ""]

    if len(weather) > 0:
        lines += day_kurz(weather[0], f"Heute · {today.strftime('%A, %d.%m.')}")
    if len(weather) > 1:
        lines += day_ausfuehrlich(weather[1], f"Morgen · {tomorrow.strftime('%A, %d.%m.')}")
    if len(weather) > 2:
        lines += day_kurz(weather[2], f"Übermorgen · {overmorrow.strftime('%A, %d.%m.')}")

    lines += ["---", "*Quelle: wttr.in*", ""]
    return "\n".join(lines)


def main():
    now = datetime.now()
    print(f"[{now.strftime('%Y-%m-%d %H:%M')}] Wetter Crawler startet...")

    sections = [
        "# Wetter – Erlangen & Nürnberg",
        f"*Zuletzt aktualisiert: {now.strftime('%d.%m.%Y %H:%M')}*",
        "",
    ]

    for city, url in CITIES.items():
        print(f"  → {city}...")
        data = fetch_weather(url)
        if not data:
            sections += [f"## 📍 {city}", "", "*Wetterdaten nicht verfügbar.*", ""]
            continue
        sections.append(build_markdown(data, city))

    md = "\n".join(sections)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(md, encoding="utf-8")
    print(f"  → {OUTPUT}")
    print(f"  → {md.count(chr(10))} Zeilen geschrieben")


if __name__ == "__main__":
    main()