# Wiesel Backend – FastAPI, LTI 1.1, Claude

Das Backend ist die zentrale Wiesel-Anwendung: Es liefert die Chat-UI aus, validiert StudOn/LTI-Launches, verwaltet Sessions in SQLite und ruft Claude Haiku 4.5 mit System-Prompt und Markdown-Wissensbasis auf.

## Stack

- FastAPI + Uvicorn
- SQLAlchemy + SQLite
- PyJWT für Session Tokens
- oauthlib für LTI-1.1/OAuth-1.0a-Signaturen
- Anthropic SDK, Modell `claude-haiku-4-5`
- Prompt Caching für System-Prompt und Wissensbasis

## Struktur

```text
backend/
├── main.py             # FastAPI app, alle zentralen Endpunkte
├── requirements.txt    # Python dependencies
├── static/chat.html    # statische Chat-UI
└── scraper/            # Hilfsskripte für Wissensquellen
```

## Endpunkte

- `GET /` – Redirect auf `/chat?debug=true`
- `GET /chat?debug=true` – lokale Debug-Session erzeugen
- `GET /chat?...` – Chat-UI ausliefern
- `POST /lti/launch` – StudOn/LTI-Launch validieren und Session erzeugen
- `POST /api/chat` – Chatnachricht verarbeiten
- `POST /api/chat/flag` – Session als auffällig markieren
- `GET /api/session/{session_id}` – Session-Metadaten für die UI
- `GET /api/wiki` – aktuell geladene Wissensbasis ausgeben
- `GET /api/logs/daily` – Tageslogs strukturiert exportieren
- `GET /health` – technischer Healthcheck

## Lokale Entwicklung

```bash
cd wiesel

docker compose up --build
```

Dann:

```text
http://localhost:8001/chat?debug=true
```

Ohne Docker:

```bash
cd backend
pip install -r requirements.txt
python main.py
```

## Environment

Datei: `backend/.env`

```env
ANTHROPIC_API_KEY=sk-ant-...
MOCK_LTI_MODE=true
JWT_SECRET=change-me
LTI_CONSUMER_KEY=test_consumer_key_mock
LTI_CONSUMER_SECRET=test_consumer_secret_mock
```

Produktion:

```env
MOCK_LTI_MODE=false
LTI_CONSUMER_KEY=...
LTI_CONSUMER_SECRET=...
JWT_SECRET=long-random-secret
```

## LTI 1.1

StudOn sendet einen signierten POST auf:

```text
/lti/launch
```

Das Backend prüft:

- Consumer Key
- OAuth-Signatur
- Timestamp-Skew
- Nonce-Wiederverwendung

Bei gültigem Launch wird eine Session in SQLite angelegt und die UI mit Token und Session-ID geöffnet.

## Claude-Integration

Das Backend lädt:

- `system-prompt.md`
- `knowledge_base/wissen-basis.md`
- weitere Markdown-Dateien unter `knowledge_base/`

Diese Inhalte werden als Systemkontext an Claude Haiku 4.5 geschickt. Der Systemkontext nutzt Anthropic Prompt Caching.

Fehlerverhalten:

- Prompt-Leak-Verdacht wird blockiert.
- Provider-/Credit-/API-Fehler werden mit Stacktrace geloggt.
- Nutzer*innen sehen nur eine neutrale technische Fallback-Antwort.

Keine internen Providerdetails im Frontend. Wir sind hier nicht im Infrastruktur-Beichtstuhl.

## Datenbank

Tabellen:

- `sessions`
- `chat_messages`
- `chat_flags`

SQLite reicht für den aktuellen Betrieb. Bei echter Last zuerst WAL, Worker und Schreibpfade prüfen. Nicht reflexhaft Postgres herbeibeschwören, nur weil es erwachsener klingt.

## Monitoring

```bash
docker compose logs -f wiesel-backend
curl http://localhost:8001/health
```

Der Healthcheck ist für Technik und Monitoring. Die UI zeigt daraus keinen Online/Offline-Status.
