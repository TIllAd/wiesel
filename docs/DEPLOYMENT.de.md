# Deployment – Wiesel

Diese Anleitung beschreibt den aktuellen Wiesel-Stack: FastAPI, statische Chat-UI, SQLite, Anthropic Claude Haiku 4.5, Docker Compose, Port `8001`. Kein separates React-Frontend. Kein OpenAI-Setup. Kein altes Architektur-Fossil mit Port 3000.

## Voraussetzungen

Auf der Zielmaschine:

- Git
- Docker mit Compose Plugin (`docker compose`)
- Zugriff auf das Repository
- Domain/Reverse Proxy, falls öffentlich betrieben
- Anthropic API-Key
- Für StudOn-Produktion: LTI Consumer Key und Secret

## Repository holen

```bash
cd /opt
git clone https://github.com/TIllAd/wiesel.git
cd wiesel
```

Falls das Repo schon existiert:

```bash
cd /opt/wiesel
git pull origin main
```

## Environment konfigurieren

Datei: `backend/.env`

Minimal für lokalen/Testbetrieb. Die LLM-Preise sind Reporting-Schätzwerte nach Claude Haiku 4.5 Public Pricing (5m Cache Write), keine Abrechnungslogik:

```env
ANTHROPIC_API_KEY=sk-ant-...
MOCK_LTI_MODE=true
JWT_SECRET=change-me-for-any-shared-environment
USD_PER_EUR=1.08
LLM_INPUT_USD_PER_MTOK=1.00
LLM_OUTPUT_USD_PER_MTOK=5.00
LLM_CACHE_WRITE_USD_PER_MTOK=1.25
LLM_CACHE_READ_USD_PER_MTOK=0.10
```

Für Produktion mit StudOn:

```env
ANTHROPIC_API_KEY=sk-ant-...
MOCK_LTI_MODE=false
LTI_CONSUMER_KEY=...
LTI_CONSUMER_SECRET=...
JWT_SECRET=long-random-secret
```

Regeln:

- `.env` niemals committen.
- `JWT_SECRET` in geteilter Umgebung immer explizit setzen.
- LTI-Secrets nur auf der Zielmaschine oder in einem echten Secret Store halten.
- Provider-/Credit-/API-Fehler gehören in Logs, nicht in Screenshots für Studierende.

## Start mit Docker Compose

```bash
docker compose up --build -d
```

Status prüfen:

```bash
docker compose ps
docker compose logs -f wiesel-backend
```

Lokal testen:

```text
http://localhost:8001/chat?debug=true
```

Healthcheck:

```bash
curl http://localhost:8001/health
```

Erwartung bei funktionierendem API-Key und erfolgreichem/noch nicht fehlgeschlagenem LLM-Zustand:

```json
{"status":"healthy","db":"connected","llm":"connected"}
```

Der Healthcheck ist technisch. Er wird nicht als Online/Offline-Status im UI angezeigt.

Kosten-/Usage-Check nach ein paar Requests:

```bash
python export_analytics.py
```

Der Export enthält dann `llm_usage` mit Request-Zahl, Tokenverbrauch, Cache-Nutzung, geschätzten EUR-Kosten, P95-Latenz und Fehleranzahl. Für Analysen wird diese JSON-Datei verwendet, nicht die Roh-DB. Ja, das ist Absicht.

## Start ohne Docker

```bash
cd backend
pip install -r requirements.txt
python main.py
```

Die App läuft dann auf:

```text
http://localhost:8001
```

## Reverse Proxy

Für öffentlichen Betrieb sollte ein Reverse Proxy TLS terminieren und auf den Backend-Port `8001` weiterleiten.

Nginx-Beispiel:

```nginx
server {
    listen 80;
    server_name chatbot-wiso.de;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name chatbot-wiso.de;

    ssl_certificate /etc/letsencrypt/live/chatbot-wiso.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chatbot-wiso.de/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Danach:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## TLS mit Let's Encrypt

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d chatbot-wiso.de
sudo systemctl enable certbot.timer
```

## StudOn / LTI 1.1

Produktionsbetrieb über:

```text
POST https://chatbot-wiso.de/lti/launch
```

Wichtig:

- In Produktion `MOCK_LTI_MODE=false` setzen.
- `LTI_CONSUMER_KEY` und `LTI_CONSUMER_SECRET` müssen exakt zu StudOn passen.
- Der Launch erzeugt eine Session und leitet auf `/chat?token=...&session_id=...` weiter.
- Nonces werden gegen Wiederverwendung geprüft.

Lokale Debug-URL bleibt:

```text
/chat?debug=true
```

## Updates deployen

```bash
cd /opt/wiesel
git pull origin main
docker compose up --build -d
docker compose logs -f wiesel-backend
```

Danach kurz testen:

```bash
curl http://localhost:8001/health
```

Und im Browser:

```text
https://chatbot-wiso.de/chat?debug=true
```

Debug-URLs nicht breit an Studierende verteilen. Überraschung: Debug ist Debug.

## Daten und Backups

Aktuell wird SQLite genutzt. Im Compose-Setup liegt die DB über Volume-Mapping bei:

```text
backend/wiesel.db -> /app/wiesel.db
```

Ein einfaches Backup:

```bash
mkdir -p /opt/wiesel-backups
sqlite3 /opt/wiesel/backend/wiesel.db ".backup '/opt/wiesel-backups/wiesel-$(date +%Y%m%d-%H%M%S).db'"
```

Cron-Beispiel:

```cron
0 2 * * * sqlite3 /opt/wiesel/backend/wiesel.db ".backup '/opt/wiesel-backups/wiesel-$(date +\%Y\%m\%d).db'"
```

Für parallele Nutzung WAL aktivieren:

```bash
sqlite3 backend/wiesel.db "PRAGMA journal_mode=WAL;"
```

## Logs und Fehleranalyse

Backend-Logs:

```bash
docker compose logs -f wiesel-backend
```

Typische Fälle:

- `Claude API error`: Provider/API/Credit/Netzwerkproblem. Sichtbar für Studierende nur als neutrale Fallback-Antwort.
- `Blocked likely system-prompt leak`: Modell wollte interne Promptteile ausgeben; Antwort wurde abgefangen.
- `LTI validation failed`: Consumer Key, Secret, Timestamp, Nonce oder Signatur prüfen.

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

LTI scheitert:

- `MOCK_LTI_MODE=false` gesetzt?
- Consumer Key korrekt?
- Consumer Secret korrekt?
- Serverzeit plausibel?
- Launch-URL exakt `/lti/launch`?

UI lädt, aber Chat antwortet nicht:

- Browser-Konsole prüfen
- `/api/session/{session_id}` testen
- `/api/chat` im Backend-Log prüfen
- Session-ID gültig?

## Skalierungshinweise

Für O-Woche/Lastspitzen:

- Reverse Proxy vor FastAPI setzen.
- Mehr Uvicorn-Worker statt unnötiger Frontend-Komplexität.
- LLM-Latenzen und Fehlerraten loggen.
- Kosten im Dashboard/Monitoring beobachten; keine versteckten Budget-Hardstops im Backend einbauen.
- SQLite beobachten; erst bei realem Druck auf Postgres migrieren.

## Betriebsprinzipien

- Kein sichtbarer Online/Offline-Badge im UI.
- Keine Provider-Namen in Nutzerantworten.
- Keine Rohchats in Berichten zitieren.
- Faktenänderungen zuerst in `knowledge_base/` pflegen.
- Tonänderungen zuerst in `system-prompt.md` pflegen.
- Deployments nach Änderungen immer mit echtem Chat-Request testen, nicht nur mit „Container läuft“. Container laufen auch, während innen Unsinn passiert. Das ist ihr Talent.
