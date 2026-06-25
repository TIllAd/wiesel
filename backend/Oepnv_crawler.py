"""
Wiesel ÖPNV Crawler
Nutzt die offizielle VAG REST-API (start.vag.de) für Abfahrten & Störungen im VGN-Netz.
Täglich um 20:00 ausführen – schreibt knowledge_base/oepnv-heute.md
Relevante Haltestellen: Erlangen, Nürnberg HBF, FAU-nahe Stops
"""

import urllib.request
import json
from datetime import datetime
from pathlib import Path

OUTPUT = Path(__file__).parent.parent / "knowledge_base" / "oepnv-heute.md"

# VAG offizielle API - kein Key nötig
VAG_BASE = "https://start.vag.de/dm/api/v1"

# Relevante Haltestellen für WiSo-Studierende
# Haltestellen-IDs: https://start.vag.de/dm/api/haltestellen.json/vgn
HALTESTELLEN = {
    "Erlangen Bahnhof":          3001,
    "Nürnberg Hauptbahnhof":      510,
    "Erlangen Arcaden":          3002,
    "Nürnberg Plärrer":          704,
}

STOERUNGEN_RSS = "https://www.vgn.de/service/stoerungen/feed/"


def fetch_json(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WieselBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  Fehler {url}: {e}")
        return None


def fetch_text(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WieselBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Fehler {url}: {e}")
        return None


def parse_stoerungen_rss(rss: str) -> list[dict]:
    """Parst VGN Störungs-RSS Feed"""
    import xml.etree.ElementTree as ET
    stoerungen = []
    try:
        root = ET.fromstring(rss)
        channel = root.find("channel")
        if channel is None:
            return []
        for item in channel.findall("item")[:5]:  # max 5
            title = item.findtext("title", "").strip()
            desc  = item.findtext("description", "").strip()
            date  = item.findtext("pubDate", "").strip()
            stoerungen.append({"title": title, "desc": desc, "date": date})
    except Exception as e:
        print(f"  RSS Parse Fehler: {e}")
    return stoerungen


def fetch_abfahrten(halt_id: int, limit: int = 4) -> list[dict]:
    """Holt nächste Abfahrten für eine Haltestelle"""
    url = f"{VAG_BASE}/abfahrten.json/vgn/{halt_id}?limitcount={limit}"
    data = fetch_json(url)
    if not data:
        return []

    abfahrten = []
    for a in data.get("Abfahrten", [])[:limit]:
        linie    = a.get("Linienname", "?")
        richtung = a.get("Richtungstext", "?")
        abf_soll = a.get("AbfahrtszeitSoll", "")
        abf_ist  = a.get("AbfahrtszeitIst", "")
        produkt  = a.get("Produkt", "")

        # Verspätung berechnen
        verspaetung = ""
        try:
            if abf_soll and abf_ist:
                from datetime import datetime as dt
                fmt = "%Y-%m-%dT%H:%M:%S"
                soll = dt.strptime(abf_soll[:19], fmt)
                ist  = dt.strptime(abf_ist[:19], fmt)
                diff = int((ist - soll).total_seconds() / 60)
                if diff > 0:
                    verspaetung = f" ⚠️ +{diff} Min."
                elif diff < 0:
                    verspaetung = f" ✅ {diff} Min."
        except Exception:
            pass

        # Uhrzeit formatieren
        uhrzeit = abf_ist[:16].replace("T", " ")[11:] if abf_ist else abf_soll[:16].replace("T", " ")[11:]

        produkt_icon = {"Bus": "🚌", "UBahn": "🚇", "Tram": "🚊", "SBahn": "🚆", "RBahn": "🚂"}.get(produkt, "🚍")

        abfahrten.append({
            "linie":      linie,
            "richtung":   richtung,
            "uhrzeit":    uhrzeit,
            "verspaetung": verspaetung,
            "icon":       produkt_icon,
        })

    return abfahrten


def build_markdown() -> str:
    now = datetime.now()

    lines = [
        "# ÖPNV VGN – Nürnberg & Erlangen",
        f"*Zuletzt aktualisiert: {now.strftime('%d.%m.%Y %H:%M')}*",
        "",
        "Verkehrsverbund Großraum Nürnberg (VGN) · Relevante Verbindungen für FAU WiSo-Studierende.",
        "",
    ]

    # Störungen
    lines += ["## Aktuelle Störungen", ""]
    rss = fetch_text(STOERUNGEN_RSS)
    if rss:
        stoerungen = parse_stoerungen_rss(rss)
        if stoerungen:
            for s in stoerungen:
                lines.append(f"### ⚠️ {s['title']}")
                if s['desc']:
                    lines.append(f"{s['desc'][:200]}")
                if s['date']:
                    lines.append(f"*{s['date']}*")
                lines.append("")
        else:
            lines += ["✅ Keine aktuellen Störungen gemeldet.", ""]
    else:
        lines += ["*Störungsdaten nicht verfügbar.*", ""]

    # Abfahrten pro Haltestelle
    lines += ["## Nächste Abfahrten (Stand Crawler-Lauf 20:00)", ""]
    lines += [
        "> **Hinweis:** Diese Daten wurden um 20:00 Uhr abgerufen.",
        "> Für Echtzeit-Abfahrten: [start.vag.de](https://start.vag.de) oder VGN App.",
        "",
    ]

    for halt_name, halt_id in HALTESTELLEN.items():
        lines.append(f"### 📍 {halt_name}")
        lines.append("")
        abfahrten = fetch_abfahrten(halt_id)
        if abfahrten:
            lines.append("| Linie | Richtung | Abfahrt | Status |")
            lines.append("|-------|----------|---------|--------|")
            for a in abfahrten:
                lines.append(f"| {a['icon']} {a['linie']} | {a['richtung']} | {a['uhrzeit']} | {a['verspaetung'] or '✅ Pünktlich'} |")
        else:
            lines.append("*Keine Abfahrtsdaten verfügbar.*")
        lines.append("")

    # Nützliche Links
    lines += [
        "## Nützliche Links",
        "",
        "- 🗺️ **Fahrplanauskunft:** [vgn.de](https://www.vgn.de)",
        "- ⚡ **Echtzeitabfahrten:** [start.vag.de](https://start.vag.de)",
        "- 🎫 **Semesterticket:** Gilt im gesamten VGN-Netz (inkl. Nürnberg, Erlangen, Fürth, Schwabach)",
        "- 📱 **App:** VGN Fahrplan & Tickets (iOS/Android)",
        "",
        "---",
        "*Quelle: VAG Echtzeitabfahrtsmonitor API / VGN Störungs-RSS*",
    ]

    return "\n".join(lines)


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ÖPNV Crawler startet...")
    md = build_markdown()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(md, encoding="utf-8")
    print(f"  → {OUTPUT}")
    print(f"  → {md.count(chr(10))} Zeilen geschrieben")


if __name__ == "__main__":
    main()