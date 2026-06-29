# Wiesel – Studienbegleiter für FAU WiSo

Wiesel ist ein KI-gestützter Studienstart-Begleiter für Studierende der FAU WiSo. Der Bot hilft bei Orientierung, Portalen, Fristen, Anlaufstellen und typischen Erstsemester-Fragen — nicht als generischer FAQ-Automat, sondern als klarer, kurzer und charaktervoller Wegweiser durchs Uni-Labyrinth.

Wichtig: Wiesel ersetzt keine offiziellen Stellen. Bei Prüfungen, Fristen, BAföG, Krankheit, Rücktritt, Rechtsfragen oder unklarer Faktenlage verweist Wiesel auf die passende offizielle Quelle.

## Produktprinzipien

- **Korrektheit vor Charakter**: Wiesel darf flink und leicht frech klingen. Bei relevanten Fakten gewinnt Präzision.
- **Kürze vor Vollständigkeitsdrang**: Erst Orientierung, dann bei Bedarf Details. Keine FAQ-Wand für einfache Fragen.
- **Datenschutz vor Neugier**: Analytics dienen der Qualitätssicherung. Rohchats sind kein Spielzeug.
- **Keine Infrastruktur-Leaks**: API-, Provider-, Credit- oder Stack-Fehler gehen ins Log, nicht an Studierende.
- **Pflege durch das Team**: Inhalte liegen als Markdown in `knowledge_base/` und können ohne Frontend-Umbau gepflegt werden.

## Aktueller Tech Stack

- **Backend**: FastAPI, Python 3.11, Uvicorn
- **LLM**: Anthropic Claude Haiku 4.5 via `anthropic` SDK
- **Prompting**: `system-prompt.md` plus Markdown-Wissensbasis aus `knowledge_base/`
- **Kosten/Performance**: Anthropic Prompt Caching für System-Prompt und Wissensbasis
- **Sessions/Logs**: SQLite über SQLAlchemy
- **Kostenkontrolle**: Token-/Cache-/Latenz-/Fehlerlogging pro LLM-Request in `llm_usage`
- **Integration**: LTI 1.1 Launch für StudOn, lokal zusätzlich Debug-Chat
- **UI**: statisches HTML/CSS/JS unter `backend/static/chat.html`, vom FastAPI-Backend ausgeliefert
- **Deployment**: Docker / Docker Compose, Standard-Port `8001`

Nicht mehr aktuell: separates React-Frontend, OpenAI/GPT-4o-mini, TF-IDF-RAG als primärer Antwortpfad. Falls du diese Begriffe noch in alten Notizen findest: archäologischer Staub. Nicht anfassen, außer zum Löschen.

## Quickstart lokal

```bash
git clone https://github.com/TIllAd/wiesel.git
cd wiesel

# .env anlegen, siehe unten
cp backend/.env.example backend/.env 2>/dev/null || true

# Docker starten
docker compose up --build
```

Dann öffnen:

```text
http://localhost:8001/chat?debug=true
```

Alternative ohne Docker:

```bash
cd backend
pip install -r requirements.txt
python main.py
```

Lokaler Backend-Port ist standardmäßig `8001`.

## Minimale Konfiguration

In `backend/.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
JWT_SECRET=change-me
MOCK_LTI_MODE=true
LTI_CONSUMER_KEY=test_consumer_key_mock
LTI_CONSUMER_SECRET=test_consumer_secret_mock
```

Für Produktion muss `MOCK_LTI_MODE=false` gesetzt und der echte StudOn/LTI Consumer Key samt Secret hinterlegt werden.

## Repository-Struktur

```text
wiesel/
├── backend/
│   ├── main.py                 # FastAPI, LTI, Chat API, SQLite, Healthcheck
│   ├── static/chat.html         # Chat-UI, Bild-/Sprachinput, Flagging
│   ├── requirements.txt
│   └── scraper/                 # Hilfsskripte für Wissensquellen
├── knowledge_base/              # Markdown-Faktenbasis für Wiesel
├── docs/
│   ├── ARCHITECTURE.de.md
│   └── DEPLOYMENT.de.md
├── system-prompt.md             # Wiesel-Identität, Ton, Sicherheitsregeln
├── Dockerfile
└── docker-compose.yml
```

## Wichtige Endpunkte

- `GET /chat?debug=true` – lokaler Testchat ohne StudOn
- `POST /lti/launch` – LTI-1.1-Launch aus StudOn
- `POST /api/chat` – Chat API
- `POST /api/chat/flag` – komplette Session als auffällig markieren
- `GET /api/session/{session_id}` – Session-Kontext für UI
- `GET /api/wiki` – geladene Wissensbasis anzeigen
- `GET /health` – technischer Healthcheck für Backend/LLM

## Kosten- und Usage-Tracking

Jeder echte LLM-Aufruf schreibt einen Datensatz in `llm_usage`: Modell, Input-/Output-Tokens, Prompt-Cache-Write, Prompt-Cache-Read, geschätzte Kosten in EUR/USD, Latenz und Fehlerklasse. Die Preise sind bewusst über `.env` konfigurierbar; sie dienen der Einordnung, nicht als Buchhaltung mit Steuerberaterhut.

`export_analytics.py` nimmt diese Usage-Daten als rohe Messdaten in die Tages-JSON-Exports auf (`analytics_YYYY-MM-DD.json`): Token-Zahlen, Kosten, Request-Counts und Session-Summen. Das Dashboard berechnet daraus Präsentationswerte wie Cent-Szenarien und Monatsprojektionen selbst. Analysen sollen diese Datei verwenden, nicht direkt die DB.

## Arbeitskultur

Wiesel ist kein Marketingbot und kein „nettes KI-Spielzeug“. Er soll Studierenden schnell helfen, ohne falsche Sicherheit zu verkaufen. Das Team pflegt Fakten vorsichtig, markiert Unsicherheit sichtbar und entscheidet lieber gegen eine schlaue Antwort als für eine erfundene.

Ton ist wichtig, aber nicht heilig. Wenn Charakter und Verlässlichkeit kollidieren, wird der Charakter gekürzt. Niedlich darf Wiesel sein; fahrlässig nicht.

## Betrieb und Qualitätssicherung

- Fehler werden intern geloggt und nach außen neutral formuliert.
- Der UI-Status zeigt kein Online/Offline-Gedöns. Wenn etwas klemmt, antwortet der Bot sauber oder der Request scheitert technisch.
- Auffällige Chats können in der UI markiert werden.
- Auswertungen sollen auf strukturierten Analytics-Exports beruhen, nicht auf neugierigem DB-Stöbern.
- Sensible Inhalte gehören nicht in Berichte und werden nicht zitiert.

## Dokumentation

- Architektur: `docs/ARCHITECTURE.de.md`
- Deployment: `docs/DEPLOYMENT.de.md`

## Lizenz

MIT.
