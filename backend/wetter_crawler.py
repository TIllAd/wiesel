"""
Wiesel Wetter Crawler
Nutzt wttr.in (kostenlos, kein API Key) für Erlangen und Nürnberg.
Täglich um 20:00 ausführen – schreibt knowledge_base/wetter-heute.md
"""

import urllib.request
import json
from datetime import datetime
from pathlib import Path

CITIES = {
    "Erlangen": "https://wttr.in/Erlangen?format=j1&lang=de",
    "Nürnberg": "https://wttr.in/Nuernberg?format=j1&lang=de",
}
OUTPUT = Path(__file__).parent.parent / "knowledge_base" / "wetter-heute.md"


def fetch_weather(url: str) -> dict | None:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "WieselBot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  Fehler beim Abrufen: {e}")
        return None


def get_schirm_empfehlung(regen_mm: float, regen_chance: int) -> str:
    if regen_chance >= 60 or regen_mm >= 2.0:
        return "🌂 **Schirm mitnehmen!** Es ist Regen wahrscheinlich."
    elif regen_chance >= 30 or regen_mm >= 0.5:
        return "🌂 Vielleicht einen Schirm einpacken, sicher ist sicher."
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
        return "🥶 Richtig kalt heute — Winterjacke, Mütze, Schal."


def get_wind_tipp(wind_kmh: int) -> str:
    if wind_kmh >= 50:
        return "💨 Starker Wind — Schirm könnte sich umdrehen!"
    elif wind_kmh >= 30:
        return "💨 Windig heute."
    return ""


def wetter_beschreibung(code: int) -> str:
    """WMO Wettercodes → deutsche Beschreibung"""
    codes = {
        113: "☀️ Sonnig",
        116: "⛅ Teilweise bewölkt",
        119: "☁️ Bewölkt",
        122: "☁️ Bedeckt",
        143: "🌫️ Neblig",
        176: "🌦️ Leichter Regenschauer",
        179: "🌨️ Leichter Schneeschauer",
        182: "🌧️ Gefrierender Regen",
        185: "🌨️ Gefrierender Nieselregen",
        200: "⛈️ Gewitter",
        227: "❄️ Schneetreiben",
        230: "❄️ Schneesturm",
        248: "🌫️ Nebel",
        260: "🌫️ Gefrierender Nebel",
        263: "🌦️ Nieselregen",
        266: "🌧️ Nieselregen",
        281: "🌧️ Gefrierender Nieselregen",
        284: "🌧️ Starker gefrierender Nieselregen",
        293: "🌦️ Leichter Regen",
        296: "🌧️ Regen",
        299: "🌧️ Mäßiger Regenschauer",
        302: "🌧️ Starker Regen",
        305: "🌧️ Starker Regenschauer",
        308: "🌧️ Sehr starker Regen",
        311: "🌧️ Gefrierender Regen",
        314: "🌧️ Starker gefrierender Regen",
        317: "🌨️ Schneeregen",
        320: "🌨️ Schnee",
        323: "🌨️ Leichter Schneefall",
        326: "❄️ Schneefall",
        329: "❄️ Mäßiger Schneefall",
        332: "❄️ Starker Schneefall",
        335: "❄️ Schneeregen",
        338: "❄️ Sehr starker Schneefall",
        350: "🌨️ Eisregen",
        353: "🌦️ Leichter Regenschauer",
        356: "🌧️ Starker Regenschauer",
        359: "🌧️ Sehr starker Regenschauer",
        362: "🌨️ Leichter Schneeregenschauer",
        365: "🌨️ Starker Schneeregenschauer",
        368: "🌨️ Leichter Schneeschauer",
        371: "❄️ Starker Schneeschauer",
        374: "🌨️ Leichter Eisregeschauer",
        377: "🌨️ Eisregeschauer",
        386: "⛈️ Gewitter mit Regen",
        389: "⛈️ Starkes Gewitter",
        392: "⛈️ Gewitter mit Schnee",
        395: "⛈️ Starkes Gewitter mit Schnee",
    }
    return codes.get(code, "🌡️ Wechselhaft")


def parse_hourly(weather_day: dict) -> list[dict]:
    """Stündliche Vorhersage für relevante Zeiten (8, 10, 12, 14, 16, 18 Uhr)"""
    relevant_times = {"800", "1000", "1200", "1400", "1600", "1800"}
    result = []
    for h in weather_day.get("hourly", []):
        t = h.get("time", "")
        if t not in relevant_times:
            continue
        result.append({
            "uhrzeit": t.zfill(4)[:2] + ":" + t.zfill(4)[2:],
            "temp": int(h.get("tempC", 0)),
            "regen_chance": int(h.get("chanceofrain", 0)),
            "wind": int(h.get("windspeedKmph", 0)),
            "code": int(h.get("weatherCode", 113)),
            "regen_mm": float(h.get("precipMM", 0)),
        })
    return result


def build_markdown(data: dict, city: str = "Erlangen") -> str:
    now = datetime.now()
    today = data["weather"][0]

    temp_max = int(today["maxtempC"])
    temp_min = int(today["mintempC"])
    avg_regen_chance = max(int(h.get("chanceofrain", 0)) for h in today.get("hourly", [{}]))
    avg_regen_mm = sum(float(h.get("precipMM", 0)) for h in today.get("hourly", []))
    avg_wind = int(sum(int(h.get("windspeedKmph", 0)) for h in today.get("hourly", [])) / max(len(today.get("hourly", [])), 1))

    schirm = get_schirm_empfehlung(avg_regen_mm, avg_regen_chance)
    temp_tipp = get_temp_tipp(temp_max, temp_min)
    wind_tipp = get_wind_tipp(avg_wind)

    hourly = parse_hourly(today)

    lines = [
        f"## 📍 {city} – {now.strftime('%A, %d.%m.%Y')}",
        "",
        "",
        "## Kurzübersicht",
        "",
        f"- 🌡️ **Temperatur:** {temp_min}°C – {temp_max}°C",
        f"- 🌧️ **Max. Regenwahrscheinlichkeit:** {avg_regen_chance}%",
        f"- 💨 **Wind:** Ø {avg_wind} km/h",
        "",
        "## Empfehlungen für heute",
        "",
        f"- {schirm}",
        f"- {temp_tipp}",
    ]

    if wind_tipp:
        lines.append(f"- {wind_tipp}")

    lines += [
        "",
        "## Stundenplan (Vorlesungszeiten)",
        "",
        "| Uhrzeit | Temp | Wetter | Regen |",
        "|---------|------|--------|-------|",
    ]

    for h in hourly:
        beschr = wetter_beschreibung(h["code"])
        regen_str = f"{h['regen_chance']}%" if h['regen_chance'] > 0 else "–"
        lines.append(f"| {h['uhrzeit']} Uhr | {h['temp']}°C | {beschr} | {regen_str} |")

    # Morgen kurz
    if len(data["weather"]) > 1:
        tomorrow = data["weather"][1]
        t_max = int(tomorrow["maxtempC"])
        t_min = int(tomorrow["mintempC"])
        t_regen = max(int(h.get("chanceofrain", 0)) for h in tomorrow.get("hourly", [{}]))
        t_schirm = get_schirm_empfehlung(
            sum(float(h.get("precipMM", 0)) for h in tomorrow.get("hourly", [])),
            t_regen
        )
        lines += [
            "",
            "## Morgen kurz",
            "",
            f"- 🌡️ {t_min}°C – {t_max}°C",
            f"- {t_schirm}",
        ]

    lines += [
        "",
        "---",
        "*Quelle: wttr.in / Open-Meteo*",
    ]

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