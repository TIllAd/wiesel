# wiesel – Studienbegleiter für WiSo FAU

Dein KI-Begleiter durchs Studium an der Friedrich-Alexander-Universität Erlangen-Nürnberg (Wirtschaftswissenschaften). **Keine generischen Antworten. Prüfungsrelevant. Ankerung in echtem Wissen — Karpathy Wiki für KI-Grundlagen, RAG mit lokaler Datenbank.**

## Features

- **Wissen, nicht Chat**: Basiert auf Karpathy-Wiki + strukturierte FAQs für WiSo-Inhalte
- **Lokal & sicher**: Alle Daten bleiben auf RRZE-Systemen, keine externen APIs nötig
- **Für Erstsemester gemacht**: Prüfungsfokussiert, keine Marketing-Sprache
- **Pflege für Nicht-Techniker**: FAQ-Updates auch ohne GitHub-Kenntnisse möglich
- **Skalierbar**: 500+ concurrent users bei Semesterstart vorbereitet

## Quickstart

```bash
# Klone das Repo
git clone https://github.com/TIllAd/wiesel.git
cd wiesel

# Lokale Entwicklung
docker-compose up -d

# Backend
cd backend && pip install -r requirements.txt && python main.py

# Frontend (separate Terminal)
cd frontend && npm install && npm start
```

Nach dem Start: http://localhost:3000

## Struktur

```
wiesel/
├── backend/            # FastAPI + TF-IDF RAG + SQLite
│   ├── main.py
│   ├── rag_engine.py   # Vektoren + Karpathy Wiki
│   ├── config.py
│   └── tests/
├── frontend/           # React Widget (für StudOn LTI 1.1)
│   └── src/
├── knowledge_base/     # FAQs + Karpathy Wiki
│   ├── karpathy_wiki.md
│   └── faqs.json
├── docs/               # Deployment, Architektur (alles Deutsch)
└── docker-compose.yml  # RRZE-ready
```

## Für Mitarbeitende

**FAQ aktualisieren?** → Siehe [BEITRÄGE.md](BEITRÄGE.md)
**Bug melden?** → [GitHub Issues](https://github.com/TIllAd/wiesel/issues/new?template=bug_report.md)
**Neue Feature-Idee?** → [Feature-Request](https://github.com/TIllAd/wiesel/issues/new?template=feature_request.md)

Alle Vorlagen sind auf Deutsch. Keine technischen Skills nötig.

## Deployment

- **Lokal**: `docker-compose up`
- **RRZE VM**: Siehe [docs/DEPLOYMENT.de.md](docs/DEPLOYMENT.de.md)
- **LTI 1.1 (StudOn)**: Phase 2, geplant nach MVP

## Lizenz

MIT – frei einsetzbar, auch für kommerzielle Weiternutzung.
