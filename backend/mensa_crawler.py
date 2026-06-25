"""
Wiesel Mensa Crawler
Nutzt die inoffizielle SigFood XML-API für die FAU Südmensa.
Täglich von Hermes ausführen – schreibt knowledge_base/mensa-heute.md
"""

import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

SIGFOOD_API = "https://www.sigfood.de/?do=api.gettagesplan&datum={date}"
OUTPUT = Path(__file__).parent.parent / "knowledge_base" / "mensa-heute.md"

WEEKDAYS = {
    0: "Montag", 1: "Dienstag", 2: "Mittwoch",
    3: "Donnerstag", 4: "Freitag"
}


def fetch_day(date_str: str) -> str | None:
    url = SIGFOOD_API.format(date=date_str)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WieselBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Fehler {date_str}: {e}")
        return None


def parse_day(xml_str: str) -> list[dict]:
    """Parst SigFood XML und gibt Liste der Gerichte zurück."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []

    gerichte = []
    tagesmenu = root.find("Tagesmenue")
    if tagesmenu is None:
        return []

    for essen in tagesmenu.findall("Mensaessen"):
        linie = essen.get("linie", "?")
        veg = essen.get("vegetarisch", "false") == "true"
        schwein = essen.get("moslem", "true") == "false"  # moslem=false → enthält Schwein

        hg = essen.find("hauptgericht")
        if hg is None:
            continue

        bez = hg.findtext("bezeichnung", "").strip()
        if not bez:
            continue

        preis_stud = hg.findtext("preisstud", "")
        preis_bed  = hg.findtext("preisbed", "")

        bewertung = hg.find("bewertung")
        schnitt = anzahl = None
        if bewertung is not None:
            schnitt = bewertung.get("schnitt")
            anzahl  = bewertung.get("anzahl")

        gerichte.append({
            "linie":      linie,
            "name":       bez,
            "veg":        veg,
            "schwein":    schwein,
            "preis_stud": f"{int(preis_stud)/100:.2f} €" if preis_stud else "",
            "preis_bed":  f"{int(preis_bed)/100:.2f} €" if preis_bed else "",
            "schnitt":    schnitt,
            "anzahl":     anzahl,
        })

    return gerichte


def format_gericht(g: dict) -> str:
    flags = []
    if g["veg"]:
        flags.append("🌱 vegetarisch")
    if g["schwein"]:
        flags.append("🐷 Schwein")

    line = f"**Linie {g['linie']}:** {g['name']}"
    if g["preis_stud"]:
        line += f" – {g['preis_stud']} (Stud.)"
        if g["preis_bed"]:
            line += f" / {g['preis_bed']} (Bed.)"
    if flags:
        line += f" _{', '.join(flags)}_"
    if g["schnitt"] and g["anzahl"] and int(g["anzahl"]) > 0:
        line += f" ⭐ {g['schnitt']}/5 ({g['anzahl']} Bew.)"
    return line


def build_markdown() -> str:
    today = datetime.now().date()
    lines = [
        "# Mensa Südmensa Erlangen – Speiseplan",
        f"*Zuletzt aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M')}*",
        "",
        "Südmensa, Erwin-Rommel-Str. 60, Erlangen. Mo–Fr 11:00–14:00 Uhr.",
        "Quelle: sigfood.de (inoffiziell) / werkswelt.de",
        "",
    ]

    found_any = False
    for i in range(7):
        day = today + timedelta(days=i)
        if day.weekday() > 4:
            continue

        date_str = day.strftime("%Y-%m-%d")
        xml_str  = fetch_day(date_str)
        if not xml_str:
            continue

        gerichte = parse_day(xml_str)
        if not gerichte:
            continue

        found_any = True
        weekday  = WEEKDAYS[day.weekday()]
        display  = day.strftime("%d.%m.%Y")
        label    = "**Heute**" if i == 0 else ("**Morgen**" if i == 1 else f"**{weekday}**")

        lines.append(f"## {label} – {weekday}, {display}")
        lines.append("")
        for g in gerichte:
            lines.append(f"- {format_gericht(g)}")
        lines.append("")

    if not found_any:
        lines.append("*Kein Speiseplan verfügbar – Mensa möglicherweise geschlossen.*")
        lines.append("")

    lines += [
        "---",
        "*Für weitere Mensen: [werkswelt.de/index.php?id=speiseplaene](https://www.werkswelt.de/index.php?id=speiseplaene)*",
    ]
    return "\n".join(lines)


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Mensa Crawler startet...")
    md = build_markdown()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(md, encoding="utf-8")
    print(f"  → {OUTPUT}")
    print(f"  → {md.count(chr(10))} Zeilen")


if __name__ == "__main__":
    main()