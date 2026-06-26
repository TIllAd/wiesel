"""
Wiesel Scraper – Kategorie C: Prüfungen, Noten & Leistungsnachweise
Speichert gecrawlte Inhalte nach: knowledge_base/pruefungen/<seite>.md
Aufruf: python pruefungen_scraper.py
Windows Task Scheduler: wöchentlich
"""

from bs4 import BeautifulSoup
import urllib.request
from datetime import date
import os

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "pruefungen")

URLS = [
    ("pruefungsamt-fau.md",      "Prüfungsamt WiSo",                  "https://www.fau.de/studium/studienorganisation/pruefungen/pruefungsamt-rw/wirtschafts-und-sozialwissenschaften/", 150),
    ("gop.md",                   "GOP – Grundlagen- und Orientierungsprüfung", "https://www.fau.de/glossary/gop-grundlagen-und-orientierungspruefung/", 80),
    ("pruefungsruecktritt.md",   "Prüfungsrücktritt",                 "https://www.fau.de/glossary/kann-ich-von-pruefungen-zuruecktreten/", 80),
    ("pruefungen-uebersicht.md", "Prüfungen Übersicht FAU",           "https://www.fau.de/studium/studienorganisation/pruefungen/#pruefungsamt", 150),
]

STATIC = [
    ("campo-bescheinigungen.md", "Bescheinigungen über campo", """Immatrikulationsbescheinigung und Notenauszug können direkt in campo heruntergeladen werden.
Login: https://www.campo.fau.de/ (mit IdM-Kennung)
Pfad in campo: Mein Studium → Bescheinigungen"""),

    ("krankmeldung.md", "Krankmeldung bei Prüfungsunfähigkeit", """Bei Krankheit zur Prüfung gilt:
- Krankschreibung innerhalb von 3 Werktagen beim Prüfungsamt einreichen
- Formular: https://www.fsi-wiso.de/wp-content/uploads/2018/05/Krankmeldung-FAU.pdf
- Prüfungsamt WiSo: Lange Gasse 20, Nürnberg (freitags geschlossen)
- Rücktritt von Prüfungen: https://www.fau.de/glossary/kann-ich-von-pruefungen-zuruecktreten/"""),
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
    print(f"\n✓ Fertig – {total} Dateien in pruefungen/")


if __name__ == "__main__":
    main()