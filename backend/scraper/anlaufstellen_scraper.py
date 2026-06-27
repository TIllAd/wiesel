"""
Wiesel Scraper – Kategorie E: Anlaufstellen & Ansprechpartner:innen
Speichert gecrawlte Inhalte nach: knowledge_base/anlaufstellen/<seite>.md
Aufruf: python anlaufstellen_scraper.py
Windows Task Scheduler: wöchentlich
"""

from bs4 import BeautifulSoup
import urllib.request
from datetime import date
import os

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "anlaufstellen")

URLS = [
    ("fachstudienberatung.md",      "Fachstudienberatung WiSo",           "https://www.wiso.rw.fau.de/studium/im-studium/fachstudienberatung/", 300),
    ("zentrale-studienberatung.md", "Zentrale Studienberatung",           "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenberatung/zentrale-studienberatung/", 150),
    ("fsi-wiso.md",                 "FSI WiSo – Fachschaft",              "https://www.fsi-wiso.de/", 80),
    ("fsi-beratung.md",             "FSI WiSo – Beratung",                "https://www.fsi-wiso.de/beratung/", 150),
    ("fsi-unileben.md",             "FSI WiSo – Unileben",                "https://www.fsi-wiso.de/unileben/", 150),
    ("studierendenwerk.md",         "Studierendenwerk Erlangen-Nürnberg", "https://www.werkswelt.de", 300),
    ("einrichtungen-wiso.md",       "Einrichtungen WiSo",                 "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/einrichtungen/", 400),
    ("mentoring.md",                "Mentoring-Programme WiSo",           "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/mentoring-programme/", 150),
]

# Statische Einträge – kein Crawling da Inhalt bereits in anderer Kategorie vorhanden
STATIC = [
    ("pruefungsamt.md", "Prüfungsamt WiSo", """Ansprechpartner für Prüfungsanmeldung, Krankmeldung, Fristen und Formulare.
Adresse: Lange Gasse 20, 90403 Nürnberg (freitags geschlossen)
Öffnungszeiten: Mo–Do 9–11 Uhr, Di zusätzlich 13–16 Uhr
Website: https://www.fau.de/studium/studienorganisation/pruefungen/pruefungsamt-rw/wirtschafts-und-sozialwissenschaften/
Detaillierte Infos zu Anmeldeterminen und Formularen: siehe knowledge_base/pruefungen/pruefungsamt-fau.md"""),
]

FALLBACKS = {
    "https://www.fsi-wiso.de/beratung/": "Die FSI WiSo bietet Beratung für Studierende an.\nHinweis: Die Unterseite wird gerade überarbeitet (Stand: Juni 2026).\nAktuelle Infos direkt bei der Fachschaft: https://www.fsi-wiso.de/\nKontakt FSI WiSo: Lange Gasse 20, Nürnberg",
    "https://www.fsi-wiso.de/unileben/": "Die FSI WiSo organisiert Events und Aktivitäten rund ums Unileben.\nHinweis: Die Unterseite wird gerade überarbeitet (Stand: Juni 2026).\nAktuelle Infos direkt bei der Fachschaft: https://www.fsi-wiso.de/",
}


def scrape(label, url, max_lines):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=10).read()
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main") or soup.find("article") or soup.find(id="content") or soup.body
        for tag in main.find_all(["nav", "header", "footer", "script", "style", "aside"]):
            tag.decompose()
        for tag in main.find_all(class_=lambda c: c and any(
            x in c for x in ["breadcrumb", "sidebar", "cookie", "banner", "menu", "navigation"]
        )):
            tag.decompose()
        lines = [l.strip() for l in main.get_text(separator="\n").splitlines()]
        lines = [l for l in lines if l and len(l) > 2]
        if len(lines) < 5 and url in FALLBACKS:
            print(f"    ⚠ Seite leer oder im Umbau – nutze Fallback")
            return FALLBACKS[url]
        return "\n".join(lines[:max_lines])
    except Exception as e:
        return f"[Fehler beim Abrufen: {e}]"


def main():
    os.makedirs(BASE_DIR, exist_ok=True)

    for filename, label, url, max_lines in URLS:
        print(f"  Scraping: {label} ...")
        text = scrape(label, url, max_lines)
        content = f"# {label}\nQuelle: {url}\nGecrawlt am: {date.today()}\n\n---\n\n{text}\n"
        with open(os.path.join(BASE_DIR, filename), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"    → {filename} ({len(text)} Zeichen)")

    for filename, label, text in STATIC:
        print(f"  Statisch: {label}")
        content = f"# {label}\nGecrawlt am: {date.today()}\n\n---\n\n{text}\n"
        with open(os.path.join(BASE_DIR, filename), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"    → {filename}")

    total = len(URLS) + len(STATIC)
    print(f"\n✓ Fertig – {total} Dateien in anlaufstellen/")


if __name__ == "__main__":
    main()