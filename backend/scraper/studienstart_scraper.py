"""
Wiesel Scraper – Kategorie A: Studienstart & Orientierung
Speichert gecrawlte Inhalte nach: knowledge_base/studienstart/<seite>.md
Aufruf: python studienstart_scraper.py
Windows Task Scheduler: wöchentlich
"""

from bs4 import BeautifulSoup
import urllib.request
from datetime import date
import os

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "studienstart")

# (dateiname, label, url, max_lines)
URLS = [
    ("studienstart-wiso.md",         "Studienstart WiSo",                          "https://www.wiso.rw.fau.de/studium/studienorganisation/studienstart/", 80),
    ("einfuehrungsveranstaltungen.md","Einführungsveranstaltungen WiSo",            "https://www.wiso.rw.fau.de/studium/studienorganisation/studienstart/einfuehrungsveranstaltungen/", 80),
    ("termine-fristen-wiso.md",       "Termine und Fristen WiSo",                   "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/termine-und-fristen/", 80),
    ("semestertermine-fau.md",        "Semestertermine FAU (Vorlesungszeiten, Fristen, Feiertage)", "https://www.fau.de/studium/studienorganisation/semestertermine/", 80),
    ("anfahrt-lageplan.md",           "Anfahrt und Lageplan",                       "https://www.wiso.rw.fau.de/anfahrt-und-lageplan/", 80),
    ("gut-zu-wissen.md",              "Gut zu wissen – Studienstart-Tipps",         "https://www.studienstart.wiso.rw.fau.de/gut-zu-wissen/", 80),
    ("infothek-a-z.md",               "Infothek A-Z Glossar",                       "https://www.infothek.rw.fau.de/a-z/", 1400),
    ("deutschlandticket.md",          "Deutschlandticket für Studierende",          "https://www.fau.de/2026/03/news/studium/deutschlandticket-ermaessigt-fuer-studierende/", 80),
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
        path = os.path.join(BASE_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"    → {filename} ({len(text)} Zeichen)")
    print(f"\n✓ Fertig – {len(URLS)} Dateien in studienstart/")


if __name__ == "__main__":
    main()