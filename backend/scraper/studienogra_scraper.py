"""
Wiesel Scraper – Kategorie B: Studienorganisation & Module
Speichert gecrawlte Inhalte nach: knowledge_base/studienorganisation/<seite>.md
Aufruf: python studienorganisation_scraper.py
Windows Task Scheduler: wöchentlich
"""

from bs4 import BeautifulSoup
import urllib.request
from datetime import date
import os

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "studienorganisation")

# (dateiname, label, url, max_lines)
URLS = [
    ("modulhandbuecher.md",   "Modulhandbücher Übersicht",       "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/modulhandbuecher/", 150),
    ("pruefungsordnungen.md", "Prüfungsordnungen WiSo",          "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/pruefungsordnungen/", 80),
    ("schwerpunktwahl.md",    "Schwerpunktwahl BA WiWi",         "https://www.ba-wiwi.wiso.rw.fau.de/", 80),
    ("auslandssemester.md",   "Auslandssemester Outgoing WiSo",  "https://www.wiso.rw.fau.de/studium/international-studierende/internationales-studium/outgoing/", 80),
    ("international-office.md","International Office WiSo",      "https://ib.wiso.fau.de", 80),
]

# Statische Einträge (JS-only oder PDFs)
STATIC = [
    ("campo.md", "campo – Verwaltungsportal", """campo ist das zentrale Verwaltungsportal der FAU.
Funktionen: Prüfungsanmeldung, Notenansicht, Stundenplanerstellung, Bescheinigungen (Immatrikulation, Notenauszug).
Login: https://www.campo.fau.de/ (mit IdM-Kennung + Passwort)
Anmeldezeitraum Prüfungen: ca. November (Wintersemester) und Mai (Sommersemester).
Anleitung Stundenplan: https://www.wiso.rw.fau.de/2023/10/05/stundenplan-erstellen-mit-campo-so-gehts/"""),

    ("modulhandbuch-pdf.md", "Modulhandbuch BA WiWi (PO 20252)", """Das Modulhandbuch beschreibt alle Module, ECTS-Punkte, Prüfungsformen und Pflichtbereiche des Bachelor Wirtschaftswissenschaften (PO 20252, gültig ab WS 2025/26).
Direktlink PDF: https://www.wiso.rw.fau.de/files/2026/03/MHB_WiWi_PO_20252_ab-WS-2025-26_V2.pdf
Übersicht aller Modulhandbücher: https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/modulhandbuecher/"""),
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
    print(f"\n✓ Fertig – {total} Dateien in studienorganisation/")


if __name__ == "__main__":
    main()