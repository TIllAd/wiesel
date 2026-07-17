"""
Wiesel FAU News & Kalender Crawler
- FAU Newsroom RSS Feed (fau.de/news)
- FAU WiSo News RSS
- Vorlesungszeiten / Semestertermine (scrape fau.de)
- Bayerische Feiertage (offizielle API: feiertage-api.de)
Täglich um 20:00 ausführen – schreibt knowledge_base/fau-aktuell.md
"""

import urllib.request
import xml.etree.ElementTree as ET
import json
import re
from datetime import datetime, date
from pathlib import Path

OUTPUT = Path(__file__).parent.parent / "knowledge_base" / "fau-aktuell.md"

FAU_NEWS_RSS  = "https://www.fau.de/feed/"
WISO_NEWS_RSS = "https://www.wiso.rw.fau.de/feed/"
FEIERTAGE_URL = "https://feiertage-api.de/api/?jahr={year}&nur_land=BY"
FAU_TERMINE_URL = "https://www.fau.de/studium/bewerbung-und-zulassung/alle-fristen-und-termine/"


def fetch_text(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WieselBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Fehler {url}: {e}")
        return None


def fetch_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WieselBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  Fehler {url}: {e}")
        return None


def parse_rss(rss: str, limit: int = 5) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(rss)
        channel = root.find("channel")
        if channel is None:
            return []
        for item in channel.findall("item")[:limit]:
            title   = item.findtext("title", "").strip()
            link    = item.findtext("link", "").strip()
            date_str = item.findtext("pubDate", "").strip()
            desc    = item.findtext("description", "").strip()
            # Strip HTML tags from description
            desc = re.sub(r'<[^>]+>', '', desc)[:150].strip()
            items.append({"title": title, "link": link, "date": date_str[:16], "desc": desc})
    except Exception as e:
        print(f"  RSS Parse Fehler: {e}")
    return items


def fetch_feiertage(year: int) -> list[dict]:
    data = fetch_json(FEIERTAGE_URL.format(year=year))
    if not data:
        return []
    feiertage = []
    today = date.today()
    for name, info in data.items():
        try:
            ft_date = datetime.strptime(info["datum"], "%Y-%m-%d").date()
            if ft_date >= today:
                feiertage.append({"name": name, "datum": ft_date})
        except Exception:
            pass
    return sorted(feiertage, key=lambda x: x["datum"])[:8]


def scrape_semestertermine(html: str) -> list[str]:
    """Extrahiert Semestertermine aus FAU HTML - fragil aber nützlich"""
    termine = []
    if not html:
        return termine

    # Suche nach Datumsmustern mit Kontext
    patterns = [
        r'(Vorlesungsbeginn[^<\n]{0,60})',
        r'(Vorlesungsende[^<\n]{0,60})',
        r'(Prüfungszeitraum[^<\n]{0,60})',
        r'(Rückmeldung[^<\n]{0,60})',
        r'(Immatrikulation[^<\n]{0,60})',
        r'(Semesterbeginn[^<\n]{0,60})',
        r'(Semesterende[^<\n]{0,60})',
        r'(Bewerbungsschluss[^<\n]{0,60})',
    ]

    html_clean = re.sub(r'<[^>]+>', ' ', html)
    html_clean = re.sub(r'\s+', ' ', html_clean)

    for pattern in patterns:
        matches = re.findall(pattern, html_clean, re.IGNORECASE)
        for m in matches[:2]:
            m = m.strip()
            if len(m) > 10 and m not in termine:
                termine.append(m)

    return termine[:12]


def build_markdown() -> str:
    now = datetime.now()
    today = date.today()

    lines = [
        "# FAU Aktuell – News & Termine",
        f"*Zuletzt aktualisiert: {now.strftime('%d.%m.%Y %H:%M')}*",
        "",
    ]

    # ── FAU WiSo News ──
    lines += ["## 📰 WiSo Fakultät – Aktuelle Meldungen", ""]
    rss = fetch_text(WISO_NEWS_RSS)
    if rss:
        items = parse_rss(rss, limit=4)
        if items:
            for item in items:
                lines.append(f"### {item['title']}")
                if item['desc']:
                    lines.append(item['desc'] + "…")
                lines.append(f"*{item['date']}* · [Weiterlesen]({item['link']})")
                lines.append("")
        else:
            lines += ["*Keine WiSo-Meldungen gefunden.*", ""]
    else:
        lines += ["*WiSo-Feed nicht verfügbar.*", ""]

    # ── FAU Newsroom ──
    lines += ["## 📰 FAU Newsroom – Universitätsnachrichten", ""]
    rss = fetch_text(FAU_NEWS_RSS)
    if rss:
        items = parse_rss(rss, limit=3)
        if items:
            for item in items:
                lines.append(f"### {item['title']}")
                if item['desc']:
                    lines.append(item['desc'] + "…")
                lines.append(f"*{item['date']}* · [Weiterlesen]({item['link']})")
                lines.append("")
        else:
            lines += ["*Keine FAU-Meldungen gefunden.*", ""]
    else:
        lines += ["*FAU-Feed nicht verfügbar.*", ""]

    # ── Semestertermine ──
    lines += ["## 📅 Semestertermine FAU", ""]
    html = fetch_text(FAU_TERMINE_URL)
    termine = scrape_semestertermine(html) if html else []
    if termine:
        for t in termine:
            lines.append(f"- {t}")
        lines.append(f"\n*Quelle: [FAU Fristen und Termine]({FAU_TERMINE_URL})*")
    else:
        # Fallback: aktuelle Semesterdaten hardcoded (WiSo Erlangen)
        lines += [
            "**Wintersemester 2025/26:**",
            "- Vorlesungsbeginn: 14. Oktober 2025",
            "- Vorlesungsende: 7. Februar 2026",
            "- Prüfungszeitraum: ca. Januar–Februar 2026",
            "- Rückmeldung WiSe 2025/26: bis 15. November 2025",
            "",
            "**Sommersemester 2026:**",
            "- Vorlesungsbeginn: 20. April 2026",
            "- Vorlesungsende: 25. Juli 2026",
            "",
            f"*Aktuelle Termine: [FAU Fristen und Termine]({FAU_TERMINE_URL})*",
        ]
    lines.append("")

    # ── Bayerische Feiertage ──
    lines += ["## 🎉 Nächste Feiertage Bayern", ""]
    feiertage = fetch_feiertage(today.year)
    # auch nächstes Jahr holen wenn kaum noch übrig
    if len(feiertage) < 3:
        feiertage += fetch_feiertage(today.year + 1)

    if feiertage:
        lines.append("| Datum | Feiertag |")
        lines.append("|-------|----------|")
        for ft in feiertage[:8]:
            delta = (ft["datum"] - today).days
            soon  = " 📌 bald!" if delta <= 14 else ""
            lines.append(f"| {ft['datum'].strftime('%d.%m.%Y')} | {ft['name']}{soon} |")
    else:
        lines += ["*Feiertagsdaten nicht verfügbar.*"]
    lines.append("")

    lines += [
        "---",
        f"*Quellen: FAU Newsroom RSS · fau.de Vorlesungszeiten · feiertage-api.de*",
    ]

    return "\n".join(lines)


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] FAU News & Kalender Crawler startet...")
    md = build_markdown()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(md, encoding="utf-8")
    print(f"  → {OUTPUT}")
    print(f"  → {md.count(chr(10))} Zeilen geschrieben")


if __name__ == "__main__":
    main()