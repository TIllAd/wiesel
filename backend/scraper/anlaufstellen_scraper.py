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
    ("fachstudienberatung.md",   "Fachstudienberatung WiSo",      "https://www.wiso.rw.fau.de/studium/im-studium/fachstudienberatung/", 150),
    ("zentrale-studienberatung.md", "Zentrale Studienberatung",   "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenberatung/zentrale-studienberatung/", 80),
    ("pruefungsamt.md",          "Prüfungsamt WiSo",              "https://www.fau.de/studium/studienorganisation/pruefungen/pruefungsamt-rw/wirtschafts-und-sozialwissenschaften/", 150),
    ("fsi-wiso.md",              "FSI WiSo – Fachschaft",         "https://www.fsi-wiso.de/", 80),
    ("studierendenwerk.md",      "Studierendenwerk Erlangen-Nürnberg", "https://www.werkswelt.de", 150),
    ("einrichtungen-wiso.md",    "Einrichtungen WiSo",            "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/einrichtungen/", 150),
    ("mentoring.md",             "Mentoring-Programme WiSo",      "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/mentoring-programme/", 80),
]


def scrape(label, url, max_lines):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=10).read()
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main") or soup.find("article") or soup.find(id="content") or soup.body
        for tag in main.find_all(["nav", "header", "footer", "script", "style", "aside"]):
            tag.decompose()
        lines = [l.strip() for l in main.get_text(separator="\n").splitlines()]
        lines = [l for l in lines if l and len(l) > 2]
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

    print(f"\n✓ Fertig – {len(URLS)} Dateien in anlaufstellen/")


if __name__ == "__main__":
    main()