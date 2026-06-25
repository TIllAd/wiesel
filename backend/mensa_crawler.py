"""
Wiesel Mensa Crawler
Holt die Mensa-Speisepläne für die nächsten 5 Werktage und schreibt sie
in knowledge_base/mensa-heute.md – täglich von Hermes ausführen.
"""
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

CANTEEN_ID = 6  # Mensa Academica Erlangen
API_BASE   = "https://api.studentenwerk-erlangen.de/openmensa/v2"
OUTPUT     = Path(__file__).parent.parent / "knowledge_base" / "mensa-heute.md"

WEEKDAYS = {
    0: "Montag", 1: "Dienstag", 2: "Mittwoch",
    3: "Donnerstag", 4: "Freitag", 5: "Samstag", 6: "Sonntag"
}

def fetch(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WieselBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  Fehler beim Abruf: {e}")
        return None

def fetch_meals(date_str: str) -> list:
    url = f"{API_BASE}/canteens/{CANTEEN_ID}/days/{date_str}/meals"
    data = fetch(url)
    return data if isinstance(data, list) else []

def format_price(prices: dict) -> str:
    p = prices.get("students") or prices.get("others")
    if p:
        return f"{float(p):.2f} €"
    return ""

def build_markdown() -> str:
    today = datetime.now().date()
    lines = [
        "# Mensa Academica Erlangen – Speiseplan",
        f"*Zuletzt aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M')}*",
        "",
        "Mensa Academica, Erwin-Rommel-Str. 60, Erlangen.",
        "Öffnungszeiten: Mo–Fr 11:00–14:00 Uhr.",
        "",
    ]
    found_any = False
    for i in range(7):  # nächste 7 Tage, Wochenende überspringen
        day = today + timedelta(days=i)
        if day.weekday() >= 5:  # Sa/So überspringen
            continue
        date_str = day.strftime("%Y-%m-%d")
        weekday  = WEEKDAYS[day.weekday()]
        display  = day.strftime("%d.%m.%Y")
        meals = fetch_meals(date_str)
        if not meals:
            continue
        found_any = True
        label = "**Heute**" if i == 0 else ("**Morgen**" if i == 1 else f"**{weekday}**")
        lines.append(f"## {label} – {weekday}, {display}")
        lines.append("")
        # Gruppiere nach Kategorie
        categories: dict[str, list] = {}
        for meal in meals:
            cat = meal.get("category", "Sonstiges")
            categories.setdefault(cat, []).append(meal)
        for cat, cat_meals in categories.items():
            lines.append(f"**{cat}**")
            for meal in cat_meals:
                name  = meal.get("name", "?")
                price = format_price(meal.get("prices", {}))
                notes = meal.get("notes", [])
                tags  = ", ".join(notes) if notes else ""
                line  = f"- {name}"
                if price:
                    line += f" – {price}"
                if tags:
                    line += f" _{tags}_"
                lines.append(line)
            lines.append("")
    if not found_any:
        lines.append("*Kein Speiseplan verfügbar – Mensa möglicherweise geschlossen oder Daten noch nicht eingetragen.*")
        lines.append("")
    lines += [
        "---",
        "*Quelle: Studentenwerk Erlangen-Nürnberg / OpenMensa API*",
    ]
    return "\n".join(lines)

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Mensa Crawler startet...")
    md = build_markdown()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(md, encoding="utf-8")
    print(f"  → Geschrieben nach {OUTPUT}")
    print(f"  → {md.count(chr(10))} Zeilen")

if __name__ == "__main__":
    main()
