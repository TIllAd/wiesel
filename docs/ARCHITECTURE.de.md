# Architektur – Wiesel

Diese Datei beschreibt den aktuellen Stand des Wiesel-Systems. Nicht den alten Wunschzettel mit React-Frontend, OpenAI und TF-IDF-RAG. Der liegt gedanklich im Museum.

## Kurzbild

```text
StudOn / Browser
      │
      │  LTI 1.1 Launch oder Debug-Chat
      ▼
FastAPI Backend :8001
      ├── statische Chat-UI aus backend/static/chat.html
      ├── /lti/launch für StudOn
      ├── /api/chat für Chatnachrichten
      ├── /api/chat/flag für Auffälligkeitsmarkierungen
      ├── /api/wiki für geladene Wissensbasis
      ├── /health für technisches Monitoring
      └── SQLite für Sessions, Chatmessages, Flags
      │
      ▼
Anthropic Claude Haiku 4.5
      ▲
      │  system-prompt.md + knowledge_base/*.md
      │  mit Prompt Caching
      │
Markdown-Wissensbasis
```

## Komponenten

### Backend

Datei: `backend/main.py`

Das Backend ist eine FastAPI-App. Sie übernimmt LTI-Launch, Session-Erzeugung, Chat-API, SQLite-Persistenz, Prompt-Zusammenbau, Anthropic-Aufruf und technische Healthchecks.

Wichtige Aufgaben:

- LTI 1.1 OAuth-1.0a-Signatur validieren, wenn `MOCK_LTI_MODE=false`.
- Debug-Sessions für lokale Tests über `/chat?debug=true` erzeugen.
- Chatverlauf pro Session in SQLite speichern.
- Wissensbasis aus `knowledge_base/` laden.
- `system-prompt.md` mit der Wissensbasis kombinieren.
- Claude Haiku 4.5 aufrufen.
- Prompt-Leakage erkennen und neutral abfangen.
- Provider-/Credit-/API-Fehler intern loggen und nur eine neutrale Fallback-Antwort ausgeben.

### Chat-UI

Datei: `backend/static/chat.html`

Die UI ist kein separates React-Projekt mehr. Sie ist eine statische HTML/CSS/JS-Datei, die direkt vom Backend ausgeliefert wird.

Funktionen:

- Chatverlauf im Browser darstellen
- Schnellfragen für typische Erstsemester-Themen
- Bildanhang per Base64 an die Chat-API
- optionale Spracheingabe über Browser-APIs
- Wiesel-Avatar-Zustände
- Chat als „auffällig“ markieren
- Session-Kontext aus `/api/session/{session_id}` anzeigen

Bewusst entfernt: Online/Offline-Badge. Der Status war mehr Kontrollillusion als Nutzen. Fehler gehören sauber in Antwort und Log, nicht als Ampel-Deko in den Header.

### LLM-Schicht

Provider: Anthropic

Modell: `claude-haiku-4-5`

Das System nutzt das Anthropic SDK und Prompt Caching:

```python
response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=1024,
    system=system_blocks,
    messages=messages,
    extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
)
```

Der System-Prompt und die Wissensbasis werden als gecachter Systemblock geschickt. Das reduziert Kosten und Latenz bei wiederholten Anfragen, besonders während Tests oder O-Woche-Last.

### Prompt und Wissensbasis

Dateien:

- `system-prompt.md`
- `knowledge_base/**/*.md`

`system-prompt.md` definiert Identität, Ton, Grenzen, Sicherheitsregeln und Verhalten bei Unsicherheit. Die Wissensbasis liefert Fakten zu Campo, StudOn, IDm, Prüfungsamt, FAUcard, BAföG, Bibliothek, Studienstart, O-Woche und Anlaufstellen.

Die Wissensbasis wird beim Request aus Markdown-Dateien geladen. `wissen-basis.md` wird bevorzugt zuerst eingefügt, danach weitere Markdown-Dateien sortiert nach Pfad.

Prinzip: Fakten kommen aus der Wissensbasis. Wenn die Wissensbasis unscharf ist, darf Wiesel nicht selbstsicher raten.

### Datenhaltung

Datenbank: SQLite

Tabellen:

- `sessions`: LTI-/Debug-Session, User-/Kurskontext, Nonce, Zeitstempel
- `chat_messages`: User- und Assistant-Nachrichten pro Session
- `chat_flags`: Session-weite Auffälligkeitsmarkierungen
- `llm_usage`: Modell, Tokenverbrauch, Prompt-Cache-Nutzung, geschätzte Kosten, Latenz und Fehlerklasse pro LLM-Request

SQLite reicht für den aktuellen MVP/Testbetrieb. Für höhere Last muss man nicht sofort eine Datenbank-Kathedrale bauen. Erst messen, dann migrieren. Alles andere ist Architekturtheater.

### Fehler- und Sicherheitsverhalten

Kritische Regeln:

- System-Prompt wird nicht ausgegeben.
- Vermutete Prompt-Leaks werden durch `SYSTEM_PROMPT_LEAK_FALLBACK` ersetzt.
- Anthropic-/Provider-/Credit-Fehler werden mit Stacktrace geloggt, aber nicht an Studierende weitergereicht.
- Die sichtbare Antwort bei LLM-Problemen ist neutral: „Gerade klemmt die Technik im Hintergrund. Versuch es bitte gleich nochmal.“
- Interne Modell-/Providerdetails gehören nicht ins Frontend.

### Healthcheck

Endpunkt: `GET /health`

Der Healthcheck ist für Docker, Monitoring und Debugging gedacht. Er ist nicht Teil der sichtbaren Nutzererfahrung.

Beispiel:

```json
{
  "status": "healthy",
  "db": "connected",
  "llm": "connected",
  "last_llm_success": "...",
  "last_llm_error": null
}
```

Wenn der LLM-Aufruf zuletzt fehlgeschlagen ist oder kein API-Key vorhanden ist, meldet der Healthcheck `unhealthy`. Das UI zeigt daraus aber keinen Badge.

### LLM-Usage und Kosten

`call_claude()` schreibt nach jedem Provider-Aufruf in `llm_usage`. Erfolgreiche Requests speichern Tokenzahlen aus `response.usage`, Prompt-Cache-Reads/Writes, geschätzte EUR/USD-Kosten und Latenz. Fehlgeschlagene Requests speichern zumindest Modell, Zeit und Fehlerklasse. Dadurch sehen Analytics später nicht nur „wie viele Chats“, sondern auch „wie teuer, wie langsam, wie kaputt“.

Die Kostenformel nutzt ENV-Werte in USD pro 1 Mio Tokens: `LLM_INPUT_USD_PER_MTOK`, `LLM_OUTPUT_USD_PER_MTOK`, `LLM_CACHE_WRITE_USD_PER_MTOK`, `LLM_CACHE_READ_USD_PER_MTOK`, plus `USD_PER_EUR`. Das ist eine Schätzung für Reporting und Dashboard-Steuerung, keine Provider-Rechnung und kein Backend-Limit. Dafür gibt es Rechnungen. Schockierend.

`export_analytics.py` exportiert globale und sessionbezogene `llm_usage`-Summen für einen Kalendertag in die JSON-Datei unter `C:\\Users\\tillt\\hermes\\analytics\\analytics_YYYY-MM-DD.json`. Standard ist heute; ein anderer Tag kann über `WIESEL_ANALYTICS_DATE=YYYY-MM-DD` gewählt werden. Der Export enthält Messdaten, keine Dashboard-Szenarien; Cent-Projektionen werden in `docs/cost-cache-model.html` berechnet. Analysen sollen diese Datei verwenden, nicht direkt die DB.

## Endpunkte

| Endpoint | Zweck |
|---|---|
| `GET /` | Redirect auf `/chat?debug=true` |
| `GET /chat?debug=true` | lokale Debug-Session starten |
| `GET /chat?...` | Chat-UI ausliefern |
| `POST /lti/launch` | StudOn/LTI-Launch entgegennehmen |
| `POST /api/chat` | Chatnachricht verarbeiten |
| `POST /api/chat/flag` | Session als auffällig markieren |
| `GET /api/session/{session_id}` | Session-Metadaten für UI |
| `GET /api/wiki` | geladene Wissensbasis anzeigen |
| `GET /api/logs/daily` | Tageslogs strukturiert exportieren |
| `GET /health` | technischer Healthcheck |

## Lokale Laufzeit

Docker Compose startet aktuell einen Backend-Container auf Port `8001`:

```bash
docker compose up --build
```

Ohne Docker:

```bash
cd backend
pip install -r requirements.txt
python main.py
```

Dann:

```text
http://localhost:8001/chat?debug=true
```

## Skalierung

Der aktuelle Engpass ist nicht HTML oder SQLite, sondern LLM-Latenz, Provider-Verfügbarkeit und Wissensbasisqualität.

Sinnvolle nächste Schritte bei Last:

1. Uvicorn/Gunicorn-Worker sauber konfigurieren.
2. SQLite WAL aktivieren und Schreibpfade beobachten.
3. Häufige statische Assets über Nginx ausliefern.
4. Missbrauchsschutz pro Session/IP nur bei realem Bedarf ergänzen; Budgetgrenzen gehören ins Dashboard/Monitoring, nicht als versteckter Backend-Hardstop.
5. Erst bei echter Schreiblast auf Postgres wechseln.

Nicht sinnvoll: ein separates Frontend oder Embedding-RAG bauen, nur weil es moderner klingt. Erst wenn die Qualitätsdaten zeigen, dass Markdown-Kontext nicht reicht.

## Projektkultur

Wiesel ist ein Studienassistenzsystem, kein Demo-Spielzeug. Die Kultur im Projekt ist: direkt, faktennah, datenschutzbewusst, wartbar für Nicht-Techniker*innen und allergisch gegen hübsche Scheinlösungen.

Bei Konflikten gilt:

1. Studierende nicht falsch leiten.
2. Offizielle Stellen nicht überstimmen.
3. Interne Technik nicht offenlegen.
4. Kurz antworten.
5. Charakter nur dort einsetzen, wo er nicht stört.
