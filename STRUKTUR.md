# Projektstruktur & Architektur

Für Entwickler und neugierige Erstis.

## Überblick

wiesel ist ein **RAG-System** (Retrieval Augmented Generation), das bedeutet:

1. **Retrieval**: Dein Input → suche ähnliche FAQs/Karpathy-Inhalte in der Datenbank
2. **Augmentation**: Kombiniere diese mit dem Kontext
3. **Generation**: Antworte präzise und quellenbasiert

**Stack:**
- Backend: Python FastAPI (async)
- Frontend: React (Widget für StudOn)
- RAG: TF-IDF Vektoren + Cosine Similarity
- Speicher: SQLite (lokal, keine externen APIs)
- Host: RRZE VM (chatbot-wiso.de)

## Verzeichnisse

```
backend/
  main.py              # FastAPI app, routes
  rag_engine.py        # TF-IDF vectorizer, search, retrieval
  config.py            # Umgebungsvariablen, Konstanten
  db/
    wiesel.db          # SQLite mit User-Feedback & History
  tests/
    test_rag_engine.py # Unit-Tests für RAG

frontend/
  public/              # Static HTML
  src/
    App.jsx            # React root
    ChatWidget.jsx     # Das Chat-Fenster
    styles.css
    index.html

knowledge_base/
  karpathy_wiki.md     # Auszug aus https://github.com/karpathy/llm.c
  faqs.json            # WiSo-spezifische FAQs (Categories A-G)
  categories.json      # Metadaten für Kategorien

docs/
  DEPLOYMENT.de.md     # Schritt-für-Schritt RRZE-Deployment
  ARCHITECTURE.de.md   # Diese Datei (technische Details)
  API.de.md            # REST-Endpoints (für Frontend-Dev)
  KARPATHY_WIKI.md     # Wie die Wiki eingebunden ist

docker-compose.yml     # Local dev & RRZE
Dockerfile             # Multi-stage build
.github/
  ISSUE_TEMPLATE/
    bug_report.md      # Bug-Report Template
    feature_request.md # Feature-Request Template
    faq_update.md      # FAQ-Update Template (für Nicht-Techniker)
```

## Datenfluss

```
User gibt Frage ein (Frontend)
  ↓
POST /api/chat (FastAPI)
  ↓
rag_engine.search(query)
  - Vektorisiere Query mit TF-IDF
  - Finde ähnlichste FAQs (cosine similarity > 0.5)
  - Finde passende Karpathy Wiki-Passagen
  ↓
Kombiniere Top 3-5 Results
  ↓
(Optional: Rufe OpenAI GPT-4o-mini auf für Final Answer)
  ↓
Antworte mit Quellen
  ↓
Speichere Feedback in SQLite (anonymisiert, kein User tracking)
```

## Kategorien (Knowledge Base)

FAQs sind nach **7 Kategorien** strukturiert:

- **A**: Allgemeines (Studienstart, Unterlagen)
- **B**: BWL-spezifisch
- **C**: Community & Networking
- **D**: Digital Tools (StudOn, Stundenplan)
- **E**: Examen & Prüfung
- **F**: Finanzen (BAföG, Stipendien)
- **G**: Grundlagen (Mathe, VWL)

Jede FAQ gehört zu genau einer Kategorie.

## RAG-Engine Details

```python
class RAGEngine:
  vectorizer = TfidfVectorizer(
    max_features=5000,
    stop_words='german',
    lowercase=True
  )
  
  def search(query: str, top_k: int = 5):
    # 1. Vektorisiere alle FAQs + Query
    query_vector = vectorizer.transform([query])
    
    # 2. Cosine Similarity gegen alle FAQs
    similarities = cosine_similarity(query_vector, faq_vectors)
    
    # 3. Filter top_k
    top_indices = argsort(similarities)[-top_k:]
    
    # 4. Gib FAQs + Confidence-Scores zurück
    return [
      {"faq_id": id, "score": score, "answer": text}
      for id, score, text in top_results
    ]
```

Keine Embedding-Modelle nötig, keine externe API — rein lokal, schnell.

## SQLite Schema

```sql
-- Feedback-Logging
CREATE TABLE interactions (
  id INTEGER PRIMARY KEY,
  timestamp DATETIME,
  query TEXT,
  faq_id TEXT,
  user_feedback INT (-1, 0, 1),  -- Daumen hoch/runter
  session_id TEXT                -- Anonymisiert
);

-- FAQs (cached aus faqs.json)
CREATE TABLE faqs (
  id TEXT PRIMARY KEY,
  kategorie TEXT,
  frage TEXT,
  antwort TEXT,
  quelle TEXT,
  tags TEXT,  -- JSON array
  updated_at DATETIME
);
```

## Deployment-Umgebungen

### Lokal (Docker Compose)

```bash
docker-compose up -d
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

### RRZE VM

```bash
# SSH auf chatbot-wiso.de
ssh admin@chatbot-wiso.de
cd /opt/wiesel
docker-compose up -d --scale backend=3
# Load Balancer: http://chatbot-wiso.de
```

Siehe [docs/DEPLOYMENT.de.md](DEPLOYMENT.de.md) für vollständige Anleitung.

## Testing

```bash
cd backend
pytest tests/ -v

# Abdeckung
pytest --cov=. tests/
```

## Limits & Skalierung

Aktuell ausgelegt für:
- **500 concurrent users** (3 Backend-Instanzen)
- **10,000 FAQs** (TF-IDF efficient bis 50k)
- **Query-Zeit: <500ms** (P95)

Bei Bedarf: mehr Backend-Replicas oder zu echtem Embedding-Modell upgraden (z.B. Sentence Transformers).

---

Fragen? Eröffne ein Issue oder schreib an Till.
