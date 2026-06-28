# Projektstruktur & Architektur

Kurzfassung: Wiesel ist aktuell ein FastAPI-basierter Studienstart-Begleiter mit statischer Chat-UI, SQLite, Markdown-Wissensbasis und Anthropic Claude Haiku 4.5. Alte Begriffe wie React-Frontend, TF-IDF-RAG oder OpenAI beschreiben nicht mehr den Produktivstand.

## Stack

- Backend: Python 3.11, FastAPI, Uvicorn
- UI: `backend/static/chat.html`, statisch vom Backend ausgeliefert
- LLM: Anthropic Claude Haiku 4.5
- Prompting: `system-prompt.md` + `knowledge_base/**/*.md`
- Performance: Anthropic Prompt Caching für System-Prompt und Wissensbasis
- Speicher: SQLite über SQLAlchemy
- Integration: LTI 1.1 für StudOn, Debug-Chat für lokale Tests
- Deployment: Docker Compose, Port `8001`

## Verzeichnisse

```text
backend/
  main.py                  # FastAPI, LTI, Chat API, SQLite, Healthcheck
  requirements.txt         # Python Dependencies
  static/chat.html         # Chat-UI
  scraper/                 # Hilfsskripte für Wissensquellen

knowledge_base/
  *.md                     # Faktenbasis für Studienstart, Portale, Orte, BAföG usw.

docs/
  ARCHITECTURE.de.md       # technische Architektur
  DEPLOYMENT.de.md         # Deployment und Betrieb

system-prompt.md           # Wiesel-Identität, Ton, Grenzen, Sicherheitsregeln
Dockerfile
docker-compose.yml
```

## Datenfluss

```text
User schreibt im Chat
  ↓
POST /api/chat
  ↓
FastAPI lädt Session + Chatverlauf aus SQLite
  ↓
FastAPI lädt Markdown-Wissensbasis
  ↓
system-prompt.md + Wissensbasis werden als gecachter Systemkontext an Claude geschickt
  ↓
Claude Haiku 4.5 erzeugt Antwort
  ↓
Backend prüft auf Prompt-Leakage und technische Fehler
  ↓
Antwort + Usernachricht werden in SQLite gespeichert
  ↓
UI zeigt Antwort
```

## Wichtige Dateien

- `backend/main.py`: zentrale Anwendung. Keine verstreute Service-Magie.
- `backend/static/chat.html`: UI inklusive Schnellfragen, Bildinput, Spracheingabe, Flagging.
- `system-prompt.md`: Produktidentität und Sicherheitsregeln.
- `knowledge_base/`: fachliche Fakten. Hier wird Wissen gepflegt, nicht im Code.
- `docs/`: Betrieb und Architektur.

## Datenbank

SQLite-Tabellen:

- `sessions`: Session-ID, LTI-Kontext, Rolle, Kurs, Nonce, Zeitstempel
- `chat_messages`: Rollenbasierte Nachrichten pro Session
- `chat_flags`: Session-weite Markierungen für Auffälligkeiten

## Lokale Entwicklung

```bash
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

## Prinzipien

- Fakten in `knowledge_base/` pflegen.
- Ton und Grenzen in `system-prompt.md` pflegen.
- Keine Providerdetails an Studierende ausgeben.
- Keine Online/Offline-Ampel im UI.
- Analytics nur strukturiert und datenschutzbewusst auswerten.
- Erst messen, dann Architektur vergrößern. Alles andere ist Beschäftigungstherapie mit YAML.
