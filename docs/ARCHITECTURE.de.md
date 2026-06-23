# wiesel-Architektur (Technische Übersicht)

## Systemdesign

```
┌─────────────────────────────────────────────────────────────┐
│                        BROWSER / LTI FRAME                   │
│                  (StudOn Integration, Phase 2)               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    HTTP/WebSocket
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
    ┌───▼────┐                          ┌────▼────┐
    │ Nginx  │◄────────────────────────►│ React   │
    │ (SSL)  │   (Port 443)              │ Widget  │
    └───┬────┘                          └────┬────┘
        │                                    │
        └────────────────┬───────────────────┘
                         │
                   REST API (/api)
                         │
        ┌────────────────▼────────────────┐
        │                                 │
    ┌───▼───────┐              ┌────────▼─────┐
    │ FastAPI   │◄────────────►│ TF-IDF RAG   │
    │ Backend   │  (Port 8000) │  Engine      │
    │ (3x)      │              │              │
    └───┬───────┘              └────┬─────────┘
        │                           │
        │                    ┌──────▼──────────┐
        │                    │ Knowledge Base  │
        │                    │                 │
        │          ┌─────────┼──────────────┐  │
        │          │         │              │  │
        │      ┌───▼───┐ ┌───▼─────┐  ┌───▼──┐│
        │      │FAQs   │ │Karpathy │  │Cache││
        │      │.json  │ │Wiki.md  │  │(LRU)││
        │      └───────┘ └─────────┘  └─────┘│
        │                                    │
        └────────────────────────────────────┘
        │
    ┌───▼──────────┐
    │ SQLite DB    │
    │ (Feedback,   │
    │  User Events)│
    └──────────────┘
```

## Component Breakdown

### 1. Frontend (React)

**Datei:** `frontend/src/ChatWidget.jsx`

```javascript
<ChatWidget>
  ├── Input Field (User Query)
  ├── Chat History Display
  │   ├── User Message
  │   ├── Bot Response (mit Quellen)
  │   └── Feedback Buttons (👍 / 👎)
  └── Category Filter (A-G)
```

**Features:**
- Material Design (kleine Komponente, für Embedding in StudOn geeignet)
- Responsive (Mobile + Desktop)
- Keine externen Dependencies (außer React)
- Real-time Feedback zum Backend

### 2. Backend (FastAPI)

**Datei:** `backend/main.py`

```python
app = FastAPI(title="wiesel")

@app.post("/api/chat")
async def chat(query: str, session_id: str):
    # 1. RAG: Suche ähnlichste FAQs
    results = rag_engine.search(query, top_k=5)
    
    # 2. Optional: GPT-4o-mini für finale Antwort
    answer = await openai_call(query, results)
    
    # 3. Speichere Feedback (anonym)
    logger.log_interaction(session_id, query, answer)
    
    return {"answer": answer, "sources": results}

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

**Stack:**
- Python 3.11+
- FastAPI (async, schnell)
- Pydantic (Validation)
- SQLAlchemy (DB-Zugriff)
- scikit-learn (TF-IDF, Cosine Similarity)

### 3. RAG Engine

**Datei:** `backend/rag_engine.py`

```python
class RAGEngine:
    def __init__(self, faqs_path: str, wiki_path: str):
        self.faqs = load_json(faqs_path)
        self.wiki = load_markdown(wiki_path)
        
        # TF-IDF Vectorizer
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='german',
            lowercase=True,
            ngram_range=(1, 2)
        )
        
        # Vektorisiere alle FAQs
        self.faq_vectors = self.vectorizer.fit_transform(
            [f['antwort'] for f in self.faqs]
        )
    
    def search(self, query: str, top_k: int = 5):
        """Finde ähnlichste FAQs"""
        query_vector = self.vectorizer.transform([query])
        
        # Cosine Similarity
        scores = cosine_similarity(query_vector, self.faq_vectors)[0]
        
        # Top K
        top_indices = np.argsort(scores)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0.1:  # Min threshold
                results.append({
                    'faq_id': self.faqs[idx]['id'],
                    'frage': self.faqs[idx]['frage'],
                    'antwort': self.faqs[idx]['antwort'],
                    'score': float(scores[idx]),
                    'kategorie': self.faqs[idx]['kategorie']
                })
        
        return results
```

**Warum TF-IDF + nicht Embeddings?**
- ✓ Keine GPU nötig, keine API-Aufrufe
- ✓ Schnell (< 50ms für 10k FAQs)
- ✓ Transparent (interpretierbar)
- ✓ Deterministisch (kein Randomness)
- ⚠ Nicht so gut bei semantischen Synonymen (z.B. "Prüfung" vs. "Exam")

**Upgrade-Pfad:** Zu Sentence Transformers, wenn nötig.

### 4. Knowledge Base

**Struktur:**

```
knowledge_base/
├── faqs.json
│   ├── ID (wiso-001, etc.)
│   ├── Kategorie (A-G)
│   ├── Frage / Antwort
│   ├── Quelle (Vorlesung, Skript)
│   ├── Tags (für Filterung)
│   └── Schwierigkeit (1-5)
│
├── karpathy_wiki.md
│   └── LLM-Grundlagen, Transformer, Attention
│
└── categories.json
    └── Metadaten für UI
```

**Format Beispiel (faqs.json):**
```json
{
  "id": "e-001",
  "kategorie": "E",
  "frage": "Welche Prüfungsformen gibt es?",
  "antwort": "Klausur (60-90 Min), mündlich, Hausarbeit, Referat, Kombination.",
  "quelle": "WiSo Modulhandbuch 2025",
  "schwierigkeit": 1,
  "tags": ["Prüfung", "Exam"]
}
```

### 5. Datenspeicherung (SQLite)

**Schema:**

```sql
-- Interaktionen / Feedback
CREATE TABLE interactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  session_id TEXT,              -- Anonyme Session
  query TEXT,
  answer_faq_id TEXT,           -- Welche FAQ wurde genutzt?
  confidence FLOAT,             -- TF-IDF Score
  user_feedback INT,            -- -1 / 0 / 1
  feedback_timestamp DATETIME
);

CREATE INDEX idx_session ON interactions(session_id);
CREATE INDEX idx_faq ON interactions(answer_faq_id);
```

**Privacyaspekte:**
- Keine IP-Adressen
- Keine Benutzer-IDs
- Session-IDs sind anonyme UUIDs
- Retention: 90 Tage, dann GDPR-konform löschen

### 6. Docker Setup

**Dockerfile (Backend):**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY knowledge_base/ ./knowledge_base/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./knowledge_base:/app/knowledge_base:ro
      - sqlite_data:/data
    environment:
      - DATABASE_PATH=/data/wiesel.db
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    restart: unless-stopped

volumes:
  sqlite_data:
```

## Anforderungen & Skalierung

### Anfrage-Verarbeitung

```
User Query
├─ Parse Input (1ms)
├─ TF-IDF Search (50ms für 10k FAQs)
├─ Optional: GPT-4o-mini Call (2-3s)
├─ Format Response (10ms)
└─ Log to SQLite (20ms)

Gesamt: ~100-200ms (ohne GPT), ~2.5s (mit GPT)
```

### Concurrent Users

**Performance Goals:**
- 500 concurrent users bei Semesterstart
- P95 Response Time: < 500ms
- Uptime: 99.9%

**Konfiguration:**
```yaml
# 3x Backend mit 4 Workers
backend:
  replicas: 3
  workers: 4
  # = 12 parallel requests
  # = ~500 users (mit pooling)
```

**Skalierung bei Bedarf:**
1. Mehr Backend-Replicas: `docker-compose up -d --scale backend=5`
2. Zu einem echten Embedding-Modell upgraden (bessere Qualität)
3. Caching-Layer (Redis) für häufige Queries

## Monitoring & Observability

**Logs:**
```bash
docker-compose logs -f backend
```

**Metriken (Optional: Prometheus):**
- `wiesel_queries_total` (Counter)
- `wiesel_response_time_ms` (Histogram)
- `wiesel_faq_hits` (Pro FAQ)

**Errors:**
- Alle Python Exceptions → logs
- Alle API Errors (400, 500) → logs + SQLite

## Security

1. **HTTPS/TLS**: Nginx mit Let's Encrypt
2. **CORS**: Nur studOn-Domänen
3. **Rate Limiting**: 100 req/min pro Session
4. **Input Validation**: Pydantic + Max Query Length
5. **SQL Injection**: SQLAlchemy ORM
6. **Environment Secrets**: .env (nicht in Git)

## LTI 1.1 Integration (Phase 2)

Geplante StudOn-Integration:

```
StudOn
  └─ LTI 1.1 Deep Link
       └─ iFrame: https://chatbot-wiso.de/lti/launch
            └─ Backend validiert LTI Signature
            └─ FrontendRendert ChatWidget
            └─ session_id = LTI user_id (anonym)
```

---

**Fragen zur Architektur?** Schreib an Till oder erstelle ein Issue.
