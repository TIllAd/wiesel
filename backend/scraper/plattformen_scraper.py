"""
Wiesel Scraper – Kategorie D: FAU-Plattformen & digitale Tools
Speichert gecrawlte Inhalte nach: knowledge_base/plattformen/<seite>.md
Aufruf: python plattformen_scraper.py
Windows Task Scheduler: wöchentlich
"""

from bs4 import BeautifulSoup
import urllib.request
from datetime import date
import os

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "plattformen")

URLS = [
    ("studon.md",           "StudOn – Lernplattform",           "https://www.studon.fau.de/", 80),
    ("idm.md",              "IdM – Identity Management",        "https://www.idm.fau.de/", 80),
    ("faumail.md",          "FAU-Mail / Studmail",              "https://faumail.fau.de", 80),
    ("eduroam.md",          "eduroam / WLAN einrichten",        "https://www.anleitungen.rrze.fau.de/internet-zugang/wlan/", 80),
    ("microsoft-office.md", "Microsoft Office 365 (RRZE)",     "https://www.rrze.fau.de/hard-software/software/microsoft/", 100),
    ("studienportale.md",   "Studienportale Übersicht WiSo",   "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/studienportale/", 80),
    ("fau-app.md",          "FAU App",                         "https://www.fau.de/universitaet/foerderung-und-unterstuetzung/alumni/die-fau-community/die-fau-community-app/", 80),
]

STATIC = [
    ("campo.md", "campo – Verwaltungsportal", """campo ist das zentrale Verwaltungsportal der FAU für alle administrativen Aufgaben.
Login: https://www.campo.fau.de/ (mit IdM-Kennung + Passwort)
Funktionen:
- Prüfungsanmeldung (Anmeldezeitraum ca. November / Mai)
- Notenansicht und Notenauszug
- Stundenplanerstellung
- Immatrikulationsbescheinigung und weitere Bescheinigungen
Anleitung Stundenplan: https://www.wiso.rw.fau.de/2023/10/05/stundenplan-erstellen-mit-campo-so-gehts/
Anleitung Prüfungsanmeldung: https://www.medizintechnik.studium.fau.de/files/2023/01/Pruefungsanmeldung-Anleitung-DE.pdf"""),
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
    print(f"\n✓ Fertig – {total} Dateien in plattformen/")


if __name__ == "__main__":
    main()