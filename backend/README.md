# Wiesel Backend – LTI 1.1 FastAPI

Minimales Backend für Wiesel-Chatbot mit LTI 1.1-Integration für StudOn.

## Stack

- **FastAPI** (async web framework)
- **SQLAlchemy + SQLite** (session management & chat history)
- **PyJWT** (session tokens)
- **oauthlib** (LTI 1.0a signature validation)
- **Anthropic Claude API** (Haiku 4.5 model)

## Architecture

```
backend/
├── main.py                 # FastAPI app, all endpoints
├── requirements.txt        # Python deps
└── .env.example           # Environment variables template
```

## Endpoints

### LTI 1.1
- `POST /lti/launch` – StudOn handshake (OAuth 1.0a signature validation)
  - Input: LTI payload from StudOn
  - Output: Redirect to `/chat?token=<jwt_token>`
  - Stores session in SQLite with user context

### Chat API
- `POST /api/chat` – Send query, get Claude response
  - Input: `{query: string, session_id: string}`
  - Output: `{response: string, session_id, timestamp}`
  - Maintains chat history per session
  - Includes Karpathy Wiki context in system prompt

- `GET /api/wiki` – Fetch Karpathy Wiki (markdown)
  - Output: `{content: markdown, format, timestamp}`

- `GET /api/session/<session_id>` – Get session metadata
  - Output: user_id, course_id, roles, timestamps

### Health
- `GET /` – Service info
- `GET /health` – Health check (for Docker/K8s)

## Local Development

### Setup

```bash
cd wiesel

# Create .env
cp backend/.env.example backend/.env
# Edit backend/.env with your keys:
# - ANTHROPIC_API_KEY=sk-your-key
# - LTI_CONSUMER_KEY/SECRET (mock for local testing)

# Install deps
pip install -r backend/requirements.txt

# Run
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```bash
docker-compose up --build
```

App runs on `http://localhost:8000`

### Testing

**Health check:**
```bash
curl http://localhost:8000/health
```

**Mock LTI Launch** (without StudOn):
```bash
# This would normally come from StudOn with OAuth 1.0a signature
# For now, test via POST /api/chat directly with a session_id
```

**Chat (direct):**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Wie melde ich mich an?", "session_id": "test-session"}'
```

**Wiki:**
```bash
curl http://localhost:8000/api/wiki
```

## LTI 1.1 Integration (StudOn)

### How it works

1. Student clicks "Wiesel" link in StudOn course
2. StudOn POSTs to `https://unwritten.chatbot-wiso.de/lti/launch` with:
   - OAuth 1.0a signature (signed with Consumer Secret)
   - LTI context: user_id, course_id, roles, user name, course name
3. Backend validates signature
4. Creates session (SQLite)
5. Generates JWT token
6. Redirects to frontend iframe: `/chat?token=<jwt>`
7. Frontend loads Chat Widget in iframe, maintains session

### Configuration (Phase 2)

When RRZE provides StudOn access:

1. Get Consumer Key/Secret from StudOn-Admin
2. Set env vars: `LTI_CONSUMER_KEY`, `LTI_CONSUMER_SECRET`
3. Register Launch URL: `https://chatbot-wiso.de/lti/launch`
4. Deploy to RRZE VM

### Security Notes

- OAuth 1.0a signature validated on every launch
- Nonce deduplicated (replay attack prevention)
- Timestamps within 1 hour checked
- JWT tokens expire after 8 hours
- All traffic HTTPS-only (Cloudflare Tunnel / RRZE)

## Database Schema

### `sessions`
- `id` (PK): JWT session ID
- `user_id`: LTI user_id (from StudOn)
- `course_id`: LTI course_id
- `user_role`: student/instructor/admin
- `user_name`, `course_name`: From LTI context
- `nonce`: OAuth nonce (dedupe)
- `created_at`, `last_accessed`: Timestamps

### `chat_messages`
- `id` (PK): Auto-increment
- `session_id` (FK): Link to session
- `role`: "user" or "assistant"
- `content`: Message text
- `created_at`: Timestamp

## Claude Integration

**Model:** `claude-3-5-haiku-20241022`
- Fast, low-cost
- 512 token max output
- System prompt includes Wiesel persona + constraints

**Context:**
- Last 4 chat messages (sliding window)
- Karpathy Wiki (first 3000 chars truncated)
- System prompt with persona + knowledge boundaries

## Karpathy Wiki Loading

- Reads from `/knowledge_base/wissen-basis.md`
- Markdown format (human & machine readable)
- Auto-included in Claude system prompt for context
- Exposed via `GET /api/wiki` for frontend visualization

## Deployment Checklist

- [ ] RRZE VM SSH access
- [ ] LTI Consumer Key/Secret from StudOn-Admin
- [ ] Domain: chatbot-wiso.de (or unwritten.chatbot-wiso.de)
- [ ] Cloudflare Tunnel configured
- [ ] ANTHROPIC_API_KEY set securely
- [ ] StudOn: Register Launch URL
- [ ] Test LTI handshake end-to-end
- [ ] Monitor logs for errors

## Monitoring

- Logs to stdout (Docker compatible)
- Health endpoint at `GET /health`
- SQLite queries logged
- Claude API errors captured

## Next Steps

1. **Frontend Chat Widget** – React component to embed in iframe
2. **Wiki Visualization** – Turn wissen-basis.md into visual Wissenslandkarte
3. **RRZE Deployment** – Docker + systemd + monitoring
4. **Feedback Loop** – Weekly cronjob analyzes chat interactions
