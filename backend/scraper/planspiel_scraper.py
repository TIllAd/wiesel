"""
Wiesel Scraper – Kategorie G: Planspiel – BizzTrainer
Speichert gecrawlte Inhalte nach: knowledge_base/planspiel/<seite>.md
Aufruf: python planspiel_scraper.py
Windows Task Scheduler: wöchentlich
"""

from bs4 import BeautifulSoup
import urllib.request
from datetime import date
import os

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "planspiel")

URLS = [
    ("bizztrainer.md",         "BizzTrainer – Planspiel-Plattform",         "https://www.bizztrainer.de/", 80),
    ("einfuehrungsveranstaltung.md", "Einführungsveranstaltung Perspektiven WiWi", "https://www.professur-wirtschaftspaedagogik.rw.fau.de/en/einfuhrung-perspektiven-der-wirtschaftswissenschaften/", 80),
]

STATIC = [
    ("spielanleitung.md", "Spielanleitung BizzTrainer", """Die Spielanleitung und weitere Dokumente zum Planspiel BizzTrainer sind im StudOn-Kurs der Einführungsveranstaltung hinterlegt.
Zugang: https://www.studon.fau.de/studon/ilias.php?baseClass=ilrepositorygui&ref_id=6014155
Hinweis: Der Zugang zu BizzTrainer (https://www.bizztrainer.de/) wird in der Einführungswoche freigeschaltet.
Bei Fragen zum Planspiel (z.B. Insolvenz des Unternehmens) bitte die Veranstaltungsleitung kontaktieren."""),
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

    for filename, label, text in STATIC:
        print(f"  Statisch: {label}")
        content = f"# {label}\nGecrawlt am: {date.today()}\n\n---\n\n{text}\n"
        with open(os.path.join(BASE_DIR, filename), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"    → {filename}")

    total = len(URLS) + len(STATIC)
    print(f"\n✓ Fertig – {total} Dateien in planspiel/")


if __name__ == "__main__":
    main()