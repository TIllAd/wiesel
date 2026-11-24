# Architektur – WiSdom

Stand: November 2026. Für Betrieb und Fehlersuche siehe [`DEPLOYMENT.de.md`](DEPLOYMENT.de.md).

## Überblick

```text
Studierende ─► https://wisdom.chatbot-wiso.de ─► Cloudflare Tunnel „wiesel-vm“
Team        ─► …/internal/ (Cloudflare Access) ─┘            │
                                                             ▼
                              RRZE-VM „wiso-chatbot“ · Docker-Container „wiesel-backend“ :8001
                              ├── FastAPI (backend/main.py)
                              ├── Chat-UI         backend/static/chat.html
                              ├── Interner Bereich backend/static/docs/internal/*
                              ├── SQLite          ~/wiesel/backend/wiesel.db  (Ordner-Mount, WAL)
                              ├── Wissensbasis    ~/wisdom-kb  →  /knowledge_base
                              └── Berichte        ~/wiesel-reports → /app/reports
                                                             │
                                                             ▼
                                              Anthropic Claude Haiku 5.5
```

## Antwortweg

1. `GET /chat` legt eine anonyme Session an und liefert die Chat-UI aus.
2. `POST /api/chat` lädt den Verlauf und baut den System-Kontext: **System-Prompt** + **Faktenbasis** (alle Wissensbasis-Dateien) + **Zusatzregeln**. Dieser Block wird gecacht (Prompt Caching). Danach folgt ungecacht das aktuelle Datum.
3. Die Antwort durchläuft Schutzfilter: Prompt-Leak-Erkennung, Quellenpflicht bei verbindlichen Themen (`evidence_guard.py`), Format- und Sicherheitsregeln.
4. Nachrichten und Tokenverbrauch (`llm_usage`) landen in SQLite. Ein Tagesbudget (`DAILY_BUDGET_EUR`) pausiert das Modell bis Mitternacht, wenn es erreicht ist.

Provider- und API-Fehler gehen ins Log. Studierende sehen nur neutrale Hinweise.

## Wissensbasis

- Markdown-Dateien, eine pro Thema. Oben steht ein Kopfbereich mit `verantwortlich` und `pruefen_bis`. Der geht **nicht** an das Modell.
- `_wisdom/system-prompt.md` und `_wisdom/regeln.md` sind Ton, Grenzen und Zusatzregeln. Sie sind im Editor unter „Verhalten von WiSdom“ bearbeitbar. Das `system-prompt.md` im Repo ist nur der Startstand für die erste Einrichtung.
- Automatische Dateien (`mensa-woche.md`, `wetter-heute.md`, `oepnv-heute.md`, `fau-aktuell.md`) erzeugt `jobs/crawl_daily.py` jede Nacht. Sind sie älter als 48 h, gehen sie nicht mehr an das Modell.
- Gelesen wird über `kb_store.py`. Ein Cache wird über Datei-Zeitstempel invalidiert, Änderungen gelten deshalb sofort.

## Interner Bereich

Geschützt durch Cloudflare Access (Pfad `/internal`) und ein daraus gesetztes Admin-Cookie für die `/api/*`-Aufrufe. Ohne Cloudflare geht es auch mit `?key=<ADMIN_API_KEY>`.

| Seite | Inhalt | API |
| --- | --- | --- |
| Wissensbasis | Editor mit Ampel, Verlauf und Wiederherstellen, Standardfragen, Ausprobieren, Link-Prüfung | `/api/kb/*` (`routers/kb_editor.py`) |
| Auffälligkeiten | Tages- und Wochenzusammenfassung, „Chat ansehen“, gemeldete Chats | `/api/review/*`, `/api/reports/range` |
| Nutzungszeiten | Nachrichten und Sessions über die Zeit | `/api/usage/timeseries` |

Jede Änderung im Editor wird mit Person (E-Mail aus Cloudflare Access), Zeit und Kommentar in `kb_versions` gespeichert.

## Nächtliche Jobs (Cron auf der VM, im Container)

| Job | Zweck |
| --- | --- |
| `jobs.chat_review` | jeden abgeschlossenen Chat bewerten, Tageszusammenfassung schreiben |
| `jobs.chat_review --weekly` | montags Wochenübersicht |
| `jobs.source_watch` | Fingerabdruck der Quellseiten vergleichen, Änderungen im Editor melden, nie Dateien ändern |
| `jobs.crawl_daily` | Mensa, Wetter, ÖPNV, FAU Aktuell |
| `db_backup.py` | SQLite-Backup mit Integritätscheck, 14 Tage |

Die VM erreicht FAU-Server nur über Ausnahmen des RRZE (Firewall-ACL). Neue Quell-Server gegebenenfalls bei acl@fau.de anfragen.

## Datenbank (SQLite)

| Tabelle | Inhalt |
| --- | --- |
| `sessions`, `chat_messages` | anonyme Sessions und Nachrichten, Löschung nach 30 Tagen |
| `chat_flags` | von Nutzer*innen gemeldete Chats, 90 Tage |
| `ueq_s_feedback` | freiwillige Kurzbewertung |
| `llm_usage` | Tokens, Cache, geschätzte Kosten, Latenz, Fehler, 90 Tage |
| `kb_versions` | Verlauf aller Änderungen im Editor |
| `kb_standardfragen` | Standardfragen und letzte Prüfergebnisse |

## Endpunkte

| Endpoint | Zweck |
| --- | --- |
| `GET /chat` | Chat-UI, legt anonyme Session an |
| `POST /api/chat` | Chatnachricht verarbeiten |
| `POST /api/chat/flag` | Chat melden |
| `POST /api/feedback/ueq-s` | Kurzbewertung |
| `GET /internal/…` | interner Bereich (Admin) |
| `/api/kb/*`, `/api/review/*`, `/api/reports/range`, `/api/usage/timeseries`, `/api/logs/daily`, `/api/session/{id}` | Admin-APIs |
| `GET /api/wiki` | aktuelle Faktenbasis als Text |
| `GET /health` | technischer Healthcheck |
