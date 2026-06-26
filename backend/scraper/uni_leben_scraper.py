"""
Wiesel Scraper – Kategorie F: Lernen, Zeitmanagement & Uni-Leben
Speichert gecrawlte Inhalte nach: knowledge_base/uni-leben/<seite>.md
Aufruf: python uni_leben_scraper.py
Windows Task Scheduler: wöchentlich
"""

from bs4 import BeautifulSoup
import urllib.request
from datetime import date
import os

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "uni-leben")

URLS = [
    ("lernraeume.md",          "Lernräume & Gruppenräume",           "https://www.infothek.rw.fau.de/glossary/lernraeume/", 80),
    ("stipendien.md",          "Stipendien & Preise WiSo",           "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/preise-und-auszeichnungen/#panel_7c29e38b", 80),
    ("bafoeg.md",              "BAföG – Studienfinanzierung",        "https://www.fau.de/studium/studienorganisation/studienfinanzierung/studienfinanzierung-mit-bafoeg/", 80),
    ("career-service.md",      "Career Service FAU",                 "https://www.career.fau.de/", 80),
    ("hochschulsport.md",      "Hochschulsport FAU",                 "https://www.hochschulsport.fau.de/", 80),
    ("psychologische-beratung.md", "Psychologisch-Psychotherapeutische Beratung", "https://www.werkswelt.de/ppb", 150),
    ("nuetzliche-apps.md",     "Nützliche Apps & Studientipps",      "https://www.studienstart.wiso.rw.fau.de/gut-zu-wissen/", 80),
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

    print(f"\n✓ Fertig – {len(URLS)} Dateien in uni-leben/")


if __name__ == "__main__":
    main()