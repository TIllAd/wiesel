"""
Wiesel Scraper – Infothek A-Z (smart, selektiv)
Zieht nur Einträge die für Erstsemester relevant sind.
Speichert eine kompakte Datei: knowledge_base/studienstart/infothek-a-z.md
Aufruf: python infothek_scraper.py
"""

from bs4 import BeautifulSoup
import urllib.request
from datetime import date
import os
import re

OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge_base", "studienstart", "infothek-a-z.md"
)

URL = "https://www.infothek.rw.fau.de/a-z/"

# Nur diese Einträge sind für Erstsemester relevant
RELEVANT_ENTRIES = {
    "BAföG",
    "Bachelorstudienberatung",
    "Bibliothek",
    "Campo",
    "Cafeteria Lange Gasse",
    "CIP-Pools",
    "Drucken",
    "ECTS",
    "Einschreibung",
    "Erste Hilfe",
    "Erstsemesterbegrüßung",
    "FAU-Card",
    "FAUbox / Datenaustausch",
    "Fachschaftsvertretung",  # FSI
    "Findelgasse",
    "Fundsachen",
    "Hausmeister",
    "IdM",
    "Infothek",
    "Kleingruppenräume Findelgasse",
    "Kopierraum",
    "Lernräume",
    "Lerninseln",
    "Mail",
    "Masterstudienberatung",
    "Mensen",
    "Mentorenprogramm",
    "Modulhandbuch",
    "Notfälle",
    "Parken",
    "Planspiele",
    "Prüfungsamt / Prüfungsverwaltung",
    "Raum der Stille",
    "Rechenzentrum (FAU RRZE)",
    "Schließfach",
    "Schwerpunktwahl Wirtschaftswissenschaften",
    "Semestertermine",
    "Sprachenzentrum Nürnberg",
    "Studienberatung",
    "Studierendenverwaltung",
    "Studieren mit Behinderung",
    "Studierendenvertretungen",
    "International Office",
}


def normalize(text):
    """Normalisiert einen Titel für Vergleich."""
    return text.strip().lower()


def is_relevant(title):
    t = normalize(title)
    for entry in RELEVANT_ENTRIES:
        if normalize(entry) in t or t in normalize(entry):
            return True
    return False


def scrape():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=15).read()
    soup = BeautifulSoup(html, "html.parser")

    # Hauptinhalt
    main = soup.find("main") or soup.find("article") or soup.body
    for tag in main.find_all(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()

    results = []
    current_title = None
    current_lines = []

    def flush():
        if current_title and is_relevant(current_title) and current_lines:
            # Kompakt auf max 30 Zeilen kürzen
            lines = [l.strip() for l in current_lines if l.strip() and len(l.strip()) > 2]
            results.append(f"## {current_title}\n\n" + "\n".join(lines[:30]))

    for elem in main.find_all(["h1", "h2", "h3", "strong", "b", "p", "li", "td", "th"]):
        tag = elem.name
        text = elem.get_text(separator=" ").strip()

        if not text:
            continue

        # Neue Sektion erkennen: bold/strong direkt in content-div, kurzer Text = Titel
        if tag in ("strong", "b") and len(text) < 80 and elem.parent.name in ("p", "div", "article", "section"):
            flush()
            current_title = text
            current_lines = []
        elif tag in ("h2", "h3") and len(text) < 80:
            # h2/h3 nur als Untertitel wenn wir schon einen Titel haben
            if current_title:
                current_lines.append(f"\n**{text}**")
            else:
                flush()
                current_title = text
                current_lines = []
        else:
            if current_title:
                current_lines.append(text)

    flush()  # Letzten Eintrag nicht vergessen

    return results


def main():
    print(f"Scraping: {URL}")
    entries = scrape()
    print(f"  → {len(entries)} relevante Einträge gefunden")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    content = f"# Infothek A-Z – Relevante Einrichtungen für Erstsemester\n"
    content += f"Quelle: {URL}\n"
    content += f"Gecrawlt am: {date.today()}\n"
    content += f"Einträge: {len(entries)}\n\n---\n\n"
    content += "\n\n---\n\n".join(entries)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"  → Gespeichert: {OUTPUT_FILE} ({size_kb:.1f} KB)")
    print(f"  → Vorher: ~71 KB | Nachher: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()