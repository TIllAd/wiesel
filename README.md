# WiSdom – KI-Navigator für den Studienstart an der FAU WiSo

WiSdom ist ein Chatbot für Erstsemester der Fakultät Wirtschafts- und Sozialwissenschaften (WiSo) der FAU Erlangen-Nürnberg. Er beantwortet Fragen rund um den Studienstart: Portale wie Campo und StudOn, Fristen, Prüfungsanmeldung, Anlaufstellen, Einführungswoche und Campusleben. Bei verbindlichen Themen wie Prüfungen, Fristen, BAföG oder Krankheit verweist er immer auf die offizielle Stelle.

**Live:** [wisdom.chatbot-wiso.de](https://wisdom.chatbot-wiso.de) · Projektleitung: Prof. Dr. Nicole Kimmelmann (Wirtschaftspädagogik) · Entwicklung: Till Adelmann

> Dieses Repository dokumentiert das Projekt und enthält den Code des laufenden Dienstes. Es ist nicht als Baukasten zum Nachbauen gedacht.

## Wie WiSdom funktioniert

- **Wissensbasis statt Internetwissen.** WiSdom antwortet aus einer kuratierten Wissensbasis mit rund 70 Themen-Dateien. Sie wird bei jeder Frage vollständig an das Sprachmodell gegeben (Kontext statt Vektorsuche). Was dort nicht steht, weiß WiSdom nicht und sagt das auch.
- **Pflege ohne Programmierkenntnisse.** Das Team bearbeitet Wissensbasis, System-Prompt und Zusatzregeln in einem Editor im geschützten internen Bereich. Änderungen gelten sofort, jede Version wird gespeichert und lässt sich zurückholen. Jede Datei hat ein „Prüfen bis“-Datum mit Ampel.
- **Qualität im Blick.** Ein nächtlicher Job bewertet alle Chats anonymisiert und schreibt eine Tages- und eine Wochenübersicht mit Wissenslücken und konkreten Aufgaben für das Team. Ein Quellen-Wächter meldet, wenn sich offizielle FAU-Seiten ändern, auf die sich die Wissensbasis stützt. Vom Team gepflegte Standardfragen prüfen, ob die wichtigsten Antworten stimmen.
- **Datenschutz.** Keine Anmeldung, keine Nutzerkonten. Chats werden nach 30 Tagen gelöscht, E-Mail-Adressen und Matrikelnummern werden in Auswertungen ausgeblendet.

```text
Studierende ──► Website (Cloudflare) ──► FastAPI-Backend auf RRZE-VM ──► Claude (Anthropic)
                                              │      ▲
                                              │      └── System-Prompt + Wissensbasis (Markdown)
Team ──► interner Bereich (Cloudflare Access) ┘          ▲
         Editor · Auffälligkeiten · Nutzung ─────────────┘
```

## Technik

| Bereich | Umsetzung |
| --- | --- |
| Backend | Python 3.11, FastAPI, SQLite |
| Sprachmodell | Anthropic Claude Haiku 5.5 mit Prompt Caching |
| Oberfläche | statisches HTML/CSS/JS, vom Backend ausgeliefert |
| Betrieb | Docker Compose auf einer VM des RRZE, öffentlich über Cloudflare Tunnel |
| Interner Bereich | Cloudflare Access (Login mit FAU-Adresse) |
| Nächtliche Jobs | Chat-Auswertung, Quellen-Wächter, Mensa/Wetter/ÖPNV/FAU-News, Backups |

## Projektgeschichte

Gestartet als RAG-Prototyp (ChromaDB, BM25, OpenAI) und als LTI-Tool in StudOn. Beides wurde ersetzt: die Vektorsuche durch eine frei editierbare Wissensbasis im Kontext, die StudOn-Einbettung durch eine eigenständige Website, die auch mobil gut funktioniert. Seit November 2026 pflegt das Team Inhalte und Verhalten selbst.

## Dokumentation

- [`docs/ARCHITECTURE.de.md`](docs/ARCHITECTURE.de.md): Aufbau, Datenfluss, Endpunkte
- [`docs/DEPLOYMENT.de.md`](docs/DEPLOYMENT.de.md): Betrieb auf der VM, Updates, Cron-Jobs, Backups, Fehlersuche
- Handbuch für das Team: separat im Projektordner

## Lizenz

MIT, siehe [LICENSE](LICENSE).
