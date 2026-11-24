# Betrieb – WiSdom

Anleitung für die Person, die WiSdom technisch betreut. Inhalte pflegt das Team selbst im Editor, dafür ist diese Datei nicht nötig.

## Wo was läuft

| Was | Wo |
| --- | --- |
| Server | RRZE-VM `wiso-chatbot` (131.188.74.146), SSH nur über FAU-VPN |
| Code | `~/wiesel` (Git-Checkout von GitHub, `main`) |
| Container | `wiesel-backend` (Docker Compose), Port 8001 |
| Öffentlich | Cloudflare Tunnel `wiesel-vm` → `wisdom.chatbot-wiso.de`, `docs.…`, `test.…` |
| Interner Bereich | `/internal`, geschützt durch Cloudflare Access (Application „docs“, Policy „Team Wiso emails“) |
| Konfiguration | `~/wiesel/backend/.env` (Geheimnisse), `~/wiesel/.env` (`WISDOM_KB_HOST_DIR`) |
| Datenbank | `~/wiesel/backend/wiesel.db` |
| Wissensbasis | `~/wisdom-kb` (vom Team im Editor gepflegt, **nicht** der Ordner im Repo) |
| Berichte, Logs, Backups | `~/wiesel-reports` |

## Konfiguration (`backend/.env`)

Pflicht in Produktion (sonst startet die App nicht): `ENVIRONMENT=production`, `ANTHROPIC_API_KEY`, `JWT_SECRET`, `ADMIN_API_KEY`. Für den Login über Cloudflare: `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`. Alles andere hat sinnvolle Standardwerte, siehe `backend/.env.example`.

Wichtige Stellschrauben:

- `ANTHROPIC_MODEL`: Modell. Wenn Anthropic ein Modell einstellt, hier wechseln und neu starten.
- `DAILY_BUDGET_EUR`: Tagesbudget, danach Pause bis Mitternacht (Standard 15).
- `CHAT_RETENTION_DAYS`, `FLAGGED_CHAT_RETENTION_DAYS`, `USAGE_RETENTION_DAYS`: Löschfristen.

`.env` niemals committen.

## Updates einspielen

Code wird nie direkt auf der VM geändert. Ablauf: Änderung am eigenen Rechner → `git push` → auf der VM:

```bash
~/deploy.sh          # git pull + docker compose up -d --build + Healthcheck
```

Danach im echten Chat eine Frage stellen. „Container läuft“ heißt noch nicht, dass WiSdom antwortet.

Healthcheck: `curl localhost:8001/health` liefert `{"status":"healthy","db":"connected","llm":"connected"}`. `llm` steht auf `disconnected`, wenn der letzte Aufruf an Anthropic fehlgeschlagen ist (Guthaben, Schlüssel, Modell).

## Daten und Backups

Die Datenbank ist SQLite im WAL-Modus. Sie liegt auf dem Host unter `~/wiesel/backend/wiesel.db` und im Container unter `/app/backend/wiesel.db` (`DATABASE_URL` in `docker-compose.yml`).

**Wichtig:** Die DB muss über ihren **Ordner** gemountet sein, nie als Einzeldatei. SQLite schreibt neue Daten zuerst in `wiesel.db-wal` daneben. Bei einem Einzeldatei-Mount (`./backend/wiesel.db:/app/wiesel.db`, so war es bis 24.11.2026) lag diese Datei nur im Container, und bei jedem Neustart gingen alle Chats seit dem letzten Checkpoint verloren. Das war die Ursache der „fehlenden Chats“.

Backup (läuft nachts per Cron, siehe unten, behält 14 Tage):

```bash
docker exec -w /app/backend wiesel-backend python db_backup.py --db /app/backend/wiesel.db --out /app/reports/db-backups
```

Vor einem Eingriff am Host von Hand erst den WAL einspielen:

```bash
docker exec wiesel-backend python -c "import sqlite3; print(sqlite3.connect('/app/backend/wiesel.db').execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone())"
```

## Wissensbasis-Editor, Crawler und Quellen-Wächter

Das Team pflegt die Wissensbasis im internen Bereich (`/internal/knowledge-base.html`). Gespeicherte Änderungen gelten sofort, ohne Neustart. Jede Version landet in der Tabelle `kb_versions` der SQLite-DB – das DB-Backup sichert damit auch den Verlauf.

**Einmalige Umstellung auf der VM** (danach nie wieder `knowledge_base/` im Repo anfassen):

```bash
cp -a ~/wiesel/knowledge_base ~/wisdom-kb
echo "WISDOM_KB_HOST_DIR=$HOME/wisdom-kb" >> ~/wiesel/.env   # .env neben docker-compose.yml, nicht backend/.env
cd ~/wiesel && docker compose up -d --build
docker exec wiesel-backend python -c "import os; print(os.listdir('/knowledge_base'))"
```

Warum: Würde der Editor in den Git-Checkout schreiben, kollidiert jeder `git pull` mit Änderungen des Teams. Der Ordner `knowledge_base/` im Repo ist ab dann nur noch der Startstand.

**Cronjobs** (`crontab -e` auf der VM):

```cron
# Mensa, Wetter, ÖPNV, FAU Aktuell – vorher liefen sie auf Tills PC
30 5 * * * docker exec -w /app/backend wiesel-backend python -m jobs.crawl_daily >> "$HOME/wiesel-reports/crawl.log" 2>&1
# Quellen-Wächter: meldet im Editor, wenn sich eine offizielle Quellseite geändert hat (ändert keine Dateien)
45 4 * * * docker exec -w /app/backend wiesel-backend python -m jobs.source_watch >> "$HOME/wiesel-reports/quellen.log" 2>&1
```

Automatische Dateien, die älter als `KB_AUTO_MAX_AGE_HOURS` (Standard 48) sind, gibt WiSdom nicht mehr an das Modell weiter und der Editor zeigt sie rot. Fällt ein Crawler aus, sagt WiSdom also lieber nichts als etwas Veraltetes.

Einmal von Hand testen:

```bash
docker exec -w /app/backend wiesel-backend python -m jobs.crawl_daily
docker exec -w /app/backend wiesel-backend python -m jobs.source_watch
```

Wer im Verlauf steht: Bei Anmeldung über Cloudflare Access die E-Mail-Adresse, beim Zugang mit Admin-Key „Team“ bzw. „Admin-Key“.

## Täglicher Chat-Review

Die Artefakte bleiben außerhalb des Repos in `~/wiesel-reports`. Das Verzeichnis muss einmal dem Benutzer gehören, der den Cronjob installiert; sonst erzeugt Docker wieder Root-Dateien, weil offenbar selbst Dateirechte ein Abenteuer sein müssen.

```bash
install -d -m 0755 -o "$(id -u)" -g "$(id -g)" ~/wiesel-reports
```

Der Job läuft mit derselben Host-UID/GID im bestehenden Container und kann daher Bericht und State schreiben, während die SQLite-DB weiter per Volume erreichbar bleibt:

```cron
15 3 * * * docker exec -u "$(id -u):$(id -g)" -w /app/backend wiesel-backend python -m jobs.chat_review >> "$HOME/wiesel-reports/cron.log" 2>&1
```

Ein Test ohne Anthropic-Aufrufe:

```bash
docker exec -u "$(id -u):$(id -g)" -w /app/backend wiesel-backend python -m jobs.chat_review --dry-run
```

Der Job bewertet jede abgeschlossene Session einzeln und schreibt danach eine **Tageszusammenfassung** nach `~/wiesel-reports/reviews/YYYY-MM-DD.md`. Das Team sieht sie im internen Bereich auf „Auffälligkeiten“. Sie ersetzt den früheren Hermes-Bericht. Abschalten mit `CHAT_REVIEW_SUMMARY=0`. Montags fasst `python -m jobs.chat_review --weekly` die letzten sieben Läufe zur Wochenübersicht zusammen (`~/wiesel-reports/weekly/YYYY-Www.md`, rund 1 Cent):

```cron
0 4 * * 1 docker exec -u "$(id -u):$(id -g)" -w /app/backend wiesel-backend python -m jobs.chat_review --weekly >> "$HOME/wiesel-reports/cron.log" 2>&1
```

In den Zusammenfassungen stehen Verweise der Form `[[chat:<Session-ID>]]`; die Seite „Auffälligkeiten“ macht daraus „Chat ansehen“. Kosten mit Haiku 5.5: rund 0,03 Cent pro Session plus etwa 0,2 Cent für die Zusammenfassung, also wenige Cent pro Tag.

## Logs und Fehleranalyse

Backend-Logs:

```bash
docker compose logs -f wiesel-backend
```

Typische Fälle:

- `Claude API error`: Provider/API/Credit/Netzwerkproblem. Sichtbar für Studierende nur als neutrale Fallback-Antwort.
- `Blocked likely system-prompt leak`: Modell wollte interne Promptteile ausgeben; Antwort wurde abgefangen.

Keine rohen API-Fehler ins UI kopieren. Das Backend ist nicht die Theaterbühne für Provider-Gedärme.

## Troubleshooting

Backend startet nicht:

```bash
docker compose logs wiesel-backend
```

Prüfen:

- existiert `backend/.env`?
- ist `ANTHROPIC_API_KEY` gesetzt?
- ist `JWT_SECRET` gesetzt?
- ist Port `8001` frei?

Healthcheck unhealthy:

```bash
curl http://localhost:8001/health
docker compose logs --tail=100 wiesel-backend
```

Mögliche Ursachen:

- kein Anthropic API-Key
- letzter LLM-Call fehlgeschlagen
- Provider/Credit/Netzwerkproblem

UI lädt, aber Chat antwortet nicht:

- Browser-Konsole prüfen
- `/api/session/{session_id}` testen
- `/api/chat` im Backend-Log prüfen
- Session-ID gültig?

## Skalierungshinweise

- Engpass ist nicht SQLite oder HTML, sondern die Antwortzeit des Modells und die Qualität der Wissensbasis.
- Für die Einführungswoche: `DAILY_BUDGET_EUR` vorher prüfen. Bei 1.000 aktiven Studierenden reicht der Standardwert eventuell nicht.
- Erst bei echtem Druck über mehr Uvicorn-Worker oder Postgres nachdenken.

## Betriebsprinzipien

- Kein sichtbarer Online/Offline-Badge im UI.
- Keine Provider-Namen in Nutzerantworten.
- Keine Rohchats in Berichten zitieren.
- Faktenänderungen im Editor pflegen (interner Bereich → Wissensbasis).
- Ton- und Regeländerungen im Editor unter „Verhalten von WiSdom“ pflegen. Die Dateien liegen im Wissensbasis-Ordner unter `_wisdom/`. Das `system-prompt.md` im Repo ist nur noch der Startstand, mit dem beim ersten Start die Datei angelegt wird.
- Deployments nach Änderungen immer mit echtem Chat-Request testen, nicht nur mit „Container läuft“. Container laufen auch, während innen Unsinn passiert. Das ist ihr Talent.
