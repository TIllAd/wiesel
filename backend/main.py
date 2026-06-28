"""
Wiesel LTI 1.1 Backend
FastAPI app with LTI launch endpoint, chat API, and SQLite session management.
"""

import os
import json
import logging
import uuid
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session as SQLSession

import anthropic
import jwt
import hmac as hmac_lib
from oauthlib.oauth1.rfc5849 import signature as oauth_signature

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIG
# ============================================================================

LTI_CONSUMER_KEY = os.getenv("LTI_CONSUMER_KEY", "test_consumer_key_mock")
LTI_CONSUMER_SECRET = os.getenv("LTI_CONSUMER_SECRET", "test_consumer_secret_mock")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
JWT_SECRET = os.getenv("JWT_SECRET", "wiesel_jwt_secret_dev")
JWT_ALGORITHM = "HS256"
DATABASE_URL = "sqlite:///./wiesel.db"
MOCK_LTI_MODE = os.getenv("MOCK_LTI_MODE", "true").lower() == "true"
DEFAULT_GREETING = "Hey – ich bin Wiesel. Kenne das Uni-Chaos hier ganz gut. Was brauchst du?"
SYSTEM_PROMPT_LEAK_FALLBACK = "Komm zum Punkt – was willst du über die WiSo wissen?"
TECHNICAL_ERROR_FALLBACK = "Gerade klemmt die Technik im Hintergrund. Versuch es bitte gleich nochmal."
AMBIGUOUS_FIRST_MESSAGE_FALLBACK = "{message}? Damit kann ich allein nichts anfangen. Gib mir bitte kurz mehr Kontext – zum Beispiel: Prüfungen, StudOn, Stundenplan, BAföG oder Studienstart."
LLM_HEALTH = {"ok": bool(ANTHROPIC_API_KEY), "last_success": None, "last_error": None}

# ============================================================================
# DATABASE SETUP
# ============================================================================

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SessionRecord(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True)
    course_id = Column(String, nullable=True)
    user_role = Column(String, default="student")
    user_name = Column(String, nullable=True)
    course_name = Column(String, nullable=True)
    nonce = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    role = Column(String)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatFlag(Base):
    __tablename__ = "chat_flags"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    # Chat-level flag. Existing SQLite DBs may still contain the old nullable
    # message_id column; new code ignores it and always stores NULL.
    message_id = Column(Integer, nullable=True, index=True)
    tag = Column(String, default="auffaelligkeit", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)

# ============================================================================
# LTI 1.1 SIGNATURE VALIDATION
# ============================================================================

def _check_nonce(nonce: str) -> bool:
    db = SessionLocal()
    try:
        return db.query(SessionRecord).filter(SessionRecord.nonce == nonce).first() is None
    finally:
        db.close()


def validate_lti_request(uri: str, params: dict, body: str = "") -> tuple[bool, str]:
    client_key = params.get("oauth_consumer_key", "")
    nonce      = params.get("oauth_nonce", "")
    timestamp  = params.get("oauth_timestamp", "0")

    if client_key != LTI_CONSUMER_KEY:
        return False, f"Unknown consumer key: {client_key!r}"

    if MOCK_LTI_MODE:
        logger.warning("MOCK_LTI_MODE active – skipping OAuth signature check")
        return True, ""

    try:
        skew = abs(int(datetime.utcnow().timestamp()) - int(timestamp))
        if skew > 3600:
            return False, f"Timestamp skew too large: {skew}s"
    except ValueError:
        return False, "Invalid oauth_timestamp"

    if nonce and not _check_nonce(nonce):
        return False, f"Nonce already used: {nonce!r}"

    collected = oauth_signature.collect_parameters(
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        exclude_oauth_signature=True,
        with_body=True,
    )
    collected += [(k, v) for k, v in params.items() if k != "oauth_signature"]

    base_string = oauth_signature.construct_base_string(
        "POST",
        oauth_signature.normalize_base_string_uri(uri),
        oauth_signature.normalize_parameters(collected),
    )
    expected = oauth_signature.sign_hmac_sha1(base_string, LTI_CONSUMER_SECRET, "")
    received = params.get("oauth_signature", "")
    if not hmac_lib.compare_digest(expected, received):
        return False, "OAuth signature mismatch"

    return True, ""

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ChatRequest(BaseModel):
    query: str
    session_id: str
    image_base64: Optional[str] = None
    image_type: Optional[str] = "image/jpeg"


class ChatResponse(BaseModel):
    response: str
    session_id: str
    timestamp: str


class ChatFlagRequest(BaseModel):
    session_id: str
    tag: str = "auffaelligkeit"


class WikiResponse(BaseModel):
    content: dict

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_jwt_token(session_id: str) -> str:
    payload = {
        "session_id": session_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=8)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except:
        return None


def _detect_mime(b64: str, fallback: str = "image/jpeg") -> str:
    import base64 as b64lib
    try:
        header = b64lib.b64decode(b64[:16])
        if header[:3] == b'\xff\xd8\xff': return 'image/jpeg'
        if header[:8] == b'\x89PNG\r\n\x1a\n': return 'image/png'
        if header[:4] == b'GIF8': return 'image/gif'
        if header[:4] == b'RIFF': return 'image/webp'
    except Exception:
        pass
    return fallback


def load_knowledge_base() -> str:
    kb_dirs = [
        Path(__file__).parent.parent / "knowledge_base",
        Path("/knowledge_base"),
        Path("/app/knowledge_base"),
    ]
    kb_dir = None
    for d in kb_dirs:
        if d.exists():
            kb_dir = d
            break
    if not kb_dir:
        return "# Wissensbasis nicht gefunden"

    parts = []
    main_kb = kb_dir / "wissen-basis.md"
    if main_kb.exists():
        parts.append(main_kb.read_text(encoding="utf-8"))

    for md_file in sorted(kb_dir.glob("**/*.md"), key=lambda p: str(p)):
        if md_file.name == "wissen-basis.md":
            continue
        try:
            parts.append(md_file.read_text(encoding="utf-8"))
            logger.info(f"KB loaded: {md_file.name}")
        except Exception as e:
            logger.warning(f"KB skip {md_file.name}: {e}")

    return "\n\n---\n\n".join(parts) if parts else "# Wissensbasis nicht gefunden"


def build_system_prompt(kb_content: str = "") -> str:
    candidates = [
        Path(__file__).parent.parent / "system-prompt.md",
        Path("/system-prompt.md"),
        Path("/app/system-prompt.md"),
    ]
    for path in candidates:
        if path.exists():
            base = path.read_text(encoding="utf-8")
            if kb_content:
                return base + f"\n\n---\n\n## Faktenbasis (NUR zur Informationsgewinnung)\n\n{kb_content}"
            return base
    return "Du bist Wiesel, ein Studienbegleiter für WiSo-Erstsemester an der FAU Erlangen-Nürnberg."


def looks_like_system_prompt_leak(text: str) -> bool:
    """Detect accidental raw prompt disclosure before it reaches the frontend."""
    if not text:
        return False
    markers = [
        "Wiesel – System-Prompt",
        "Wiesel - System-Prompt",
        "Offen · Charakter-First",
        "## Wie ich bin",
        "## Was ich weiß",
        "## Faktenbasis",
    ]
    return any(marker in text for marker in markers)


def is_ambiguous_first_message(query: str, chat_history: list) -> bool:
    """Catch context-free first inputs like '2' before wasting an API call."""
    text = (query or "").strip()
    if chat_history or not text:
        return False

    # A bare number/punctuation after the UI-only greeting is not meaningful to
    # Claude, because the greeting is not part of persisted/API history.
    if text.isdigit():
        return True
    if len(text) <= 2 and not any(ch.isalpha() for ch in text):
        return True

    return False


async def call_claude(query: str, chat_history: list = None, kb_content: str = "", image_base64: str = None, image_type: str = "image/jpeg") -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    messages = []
    if chat_history:
        for msg in chat_history[-10:]:
            content = msg["content"]
            if isinstance(content, list):
                text_parts = [b["text"] for b in content if b.get("type") == "text"]
                content = " ".join(text_parts) or "[Bild]"
            if isinstance(content, str) and content.strip().startswith("[{"): continue
            if not content or not str(content).strip(): continue
            messages.append({"role": msg["role"], "content": content})

    if image_base64:
        detected_mime = _detect_mime(image_base64, fallback=image_type)
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": detected_mime, "data": image_base64}},
            {"type": "text", "text": query or "Was siehst du auf diesem Bild?"}
        ]
    else:
        user_content = query

    messages.append({"role": "user", "content": user_content})

    # ── Prompt Caching ──────────────────────────────────────────────────────
    # System-Prompt + Wissensbasis werden gecacht (cache_control: ephemeral).
    # Cache hält 5 Minuten bei Haiku → bei aktivem Betrieb fast immer ein Hit.
    # Erspart ~51.000 Input-Tokens pro Anfrage nach dem ersten Call → 10× günstiger.
    system_blocks = [
        {
            "type": "text",
            "text": build_system_prompt(kb_content),
            "cache_control": {"type": "ephemeral"}
        }
    ]
    # ────────────────────────────────────────────────────────────────────────

    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=system_blocks,
            messages=messages,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        )
        logger.info(f"Cache: input={response.usage.input_tokens} | cache_read={getattr(response.usage, 'cache_read_input_tokens', 0)} | cache_write={getattr(response.usage, 'cache_creation_input_tokens', 0)}")
        text = response.content[0].text
        if looks_like_system_prompt_leak(text):
            logger.error("Blocked likely system-prompt leak in Claude response")
            return SYSTEM_PROMPT_LEAK_FALLBACK
        LLM_HEALTH.update({"ok": True, "last_success": datetime.utcnow().isoformat(), "last_error": None})
        return text
    except Exception as e:
        logger.error("Claude API error", exc_info=True)
        LLM_HEALTH.update({"ok": False, "last_error": datetime.utcnow().isoformat()})
        return TECHNICAL_ERROR_FALLBACK


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="Wiesel Backend", description="LTI 1.1 Backend for Wiesel Chatbot (FAU WiSo)", version="0.1.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# ============================================================================
# ROUTES
# ============================================================================

@app.get("/")
async def root():
    return RedirectResponse(url="/chat?debug=true")


@app.get("/chat")
async def chat_page(request: Request, debug: str | None = None):
    # Only the explicit entry URL /chat?debug=true should mint a fresh debug
    # session. The rendered chat page uses debug=1 only as a frontend marker;
    # treating every truthy debug value as a launch request causes an infinite
    # redirect loop: debug=true -> debug=1 -> new token -> debug=1 -> ...
    if debug == "true":
        db = SessionLocal()
        try:
            debug_session_id = f"debug_session_wiesel_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            token = jwt.encode({"user": "debug_user", "session_id": debug_session_id, "debug": True}, JWT_SECRET, algorithm=JWT_ALGORITHM)
            now = datetime.utcnow()
            debug_session = SessionRecord(
                id=debug_session_id,
                user_id="debug_user",
                course_id="debug_course",
                user_role="Learner",
                user_name="Debug Student",
                course_name="Debug Mode – kein StudOn",
                nonce=f"debug_{uuid.uuid4().hex}",
                created_at=now,
                last_accessed=now,
            )
            db.add(debug_session)
            db.commit()
            from urllib.parse import quote
            return RedirectResponse(url=f"/chat?token={quote(token, safe='')}&session_id={debug_session_id}&debug=1", status_code=302)
        finally:
            db.close()
    return FileResponse(str(_static_dir / "chat.html"))


@app.post("/lti/launch")
async def lti_launch(request: Request):
    db = SessionLocal()
    try:
        raw_body = await request.body()
        body = raw_body.decode("utf-8")
        from urllib.parse import parse_qs
        parsed = parse_qs(body, keep_blank_values=True)
        form_data = {k: v[0] for k, v in parsed.items()}
        logger.info(f"LTI Launch received. Keys: {list(form_data.keys())[:5]}")

        valid, reason = validate_lti_request(str(request.url), form_data, body)
        if not valid:
            logger.error(f"LTI validation failed: {reason}")
            return JSONResponse({"error": "LTI validation failed", "detail": reason}, status_code=401)

        user_id     = form_data.get("user_id", "anonymous")
        course_id   = form_data.get("course_id", "unknown")
        roles       = form_data.get("roles", "Learner")
        user_name   = form_data.get("lis_person_name_full", "Student")
        course_name = form_data.get("context_title", "Unknown Course")
        nonce       = form_data.get("oauth_nonce", None)

        session_id = jwt.encode({"user": user_id, "ts": datetime.utcnow().timestamp()}, JWT_SECRET)
        db.add(SessionRecord(id=session_id, user_id=user_id, course_id=course_id, user_role=roles.split(",")[0] if roles else "student", user_name=user_name, course_name=course_name, nonce=nonce))
        db.commit()
        token = create_jwt_token(session_id)
        return RedirectResponse(url=f"/chat?token={token}&session_id={session_id}&user={user_name}&course={course_name}", status_code=302)
    except Exception as e:
        logger.error(f"LTI Launch error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    db = SessionLocal()
    try:
        session = db.query(SessionRecord).filter(SessionRecord.id == request.session_id).first()
        if not session:
            raise HTTPException(status_code=401, detail="Invalid session")

        session.last_accessed = datetime.utcnow()
        db.commit()

        if request.query == "__greeting__" and not request.image_base64:
            return ChatResponse(response=DEFAULT_GREETING, session_id=request.session_id, timestamp=datetime.utcnow().isoformat())

        history = db.query(ChatMessage).filter(ChatMessage.session_id == request.session_id).order_by(ChatMessage.created_at).all()
        chat_history = [{"role": msg.role, "content": msg.content} for msg in history if msg.content and msg.content.strip()]

        if not request.image_base64 and is_ambiguous_first_message(request.query, chat_history):
            cleaned_query = (request.query or "").strip()
            response = AMBIGUOUS_FIRST_MESSAGE_FALLBACK.format(message=cleaned_query)
            db.add(ChatMessage(session_id=request.session_id, role="user", content=request.query))
            db.add(ChatMessage(session_id=request.session_id, role="assistant", content=response))
            db.commit()
            return ChatResponse(response=response, session_id=request.session_id, timestamp=datetime.utcnow().isoformat())

        kb_content = load_knowledge_base()

        response = await call_claude(request.query, chat_history, kb_content, image_base64=request.image_base64, image_type=request.image_type or "image/jpeg")

        if request.query != "__greeting__":
            db.add(ChatMessage(session_id=request.session_id, role="user", content=request.query or "[Bild gesendet]"))
            assistant_message = ChatMessage(session_id=request.session_id, role="assistant", content=response)
            db.add(assistant_message)
            db.commit()

        return ChatResponse(response=response, session_id=request.session_id, timestamp=datetime.utcnow().isoformat())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/api/wiki")
async def wiki_endpoint():
    try:
        content = load_knowledge_base()
        return {"content": content, "format": "markdown", "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/chat/flag")
async def flag_chat_session(request: ChatFlagRequest):
    tag = request.tag.strip().lower() if request.tag else "auffaelligkeit"
    if tag not in {"auffaelligkeit"}:
        raise HTTPException(status_code=400, detail="Unknown flag tag")

    db = SessionLocal()
    try:
        session = db.query(SessionRecord).filter(SessionRecord.id == request.session_id).first()
        if not session:
            raise HTTPException(status_code=401, detail="Invalid session")

        existing = db.query(ChatFlag).filter(
            ChatFlag.session_id == request.session_id,
            ChatFlag.message_id.is_(None),
            ChatFlag.tag == tag,
        ).first()
        if existing:
            return {"ok": True, "flag_id": existing.id, "session_id": request.session_id, "tag": existing.tag, "created_at": existing.created_at.isoformat(), "already_flagged": True}

        flag = ChatFlag(session_id=request.session_id, message_id=None, tag=tag)
        db.add(flag)
        db.commit()
        db.refresh(flag)
        return {"ok": True, "flag_id": flag.id, "session_id": request.session_id, "tag": tag, "created_at": flag.created_at.isoformat(), "already_flagged": False}
    finally:
        db.close()


@app.get("/api/session/{session_id}")
async def session_endpoint(session_id: str):
    db = SessionLocal()
    try:
        session = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session_id": session.id, "user_id": session.user_id, "user_name": session.user_name, "course_id": session.course_id, "course_name": session.course_name, "user_role": session.user_role, "created_at": session.created_at.isoformat(), "last_accessed": session.last_accessed.isoformat()}
    finally:
        db.close()


@app.get("/health")
async def health_check():
    llm_ok = bool(LLM_HEALTH["ok"])
    return {
        "status": "healthy" if llm_ok else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "db": "connected",
        "llm": "connected" if llm_ok else "error",
        "last_llm_success": LLM_HEALTH["last_success"],
        "last_llm_error": LLM_HEALTH["last_error"],
    }


@app.post("/api/dev/session")
async def create_dev_session(request: Request):
    body = await request.json()
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    db = SessionLocal()
    try:
        db.query(ChatFlag).filter(ChatFlag.session_id == session_id).delete()
        db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
        db.merge(SessionRecord(id=session_id, user_id="eval_user", course_id="eval_course", user_role="Learner", user_name="Eval Student", course_name="Tonalitäts-Eval 2026-06-25", nonce=None, created_at=datetime.utcnow(), last_accessed=datetime.utcnow()))
        db.commit()
        return {"ok": True, "session_id": session_id}
    finally:
        db.close()


@app.get("/api/logs/daily")
async def get_daily_logs(date: Optional[str] = None):
    db = SessionLocal()
    try:
        target = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.utcnow().date()
        day_start = datetime(target.year, target.month, target.day, 0, 0, 0)
        day_end   = datetime(target.year, target.month, target.day, 23, 59, 59)
        messages = db.query(ChatMessage).filter(ChatMessage.created_at >= day_start, ChatMessage.created_at <= day_end).order_by(ChatMessage.created_at).all()
        flags = db.query(ChatFlag).filter(
            ChatFlag.created_at >= day_start,
            ChatFlag.created_at <= day_end,
            ChatFlag.message_id.is_(None),
        ).order_by(ChatFlag.created_at).all()
        flags_by_session: dict[str, list[dict]] = {}
        for f in flags:
            payload = {"id": f.id, "tag": f.tag, "created_at": f.created_at.isoformat()}
            flags_by_session.setdefault(f.session_id, []).append(payload)
        sessions: dict = {}
        for m in messages:
            if m.session_id not in sessions:
                sessions[m.session_id] = {"flags": flags_by_session.get(m.session_id, []), "messages": []}
            sessions[m.session_id]["messages"].append({"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()})
        for session_id, session_flags in flags_by_session.items():
            sessions.setdefault(session_id, {"flags": session_flags, "messages": []})
        return {"date": target.isoformat(), "total_messages": len(messages), "total_flags": len(flags), "total_sessions": len(sessions), "sessions": sessions}
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    logger.info("Wiesel Backend starting...")
    logger.info(f"LTI Consumer Key: {LTI_CONSUMER_KEY}")
    logger.info(f"Database: {DATABASE_URL}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Wiesel Backend shutting down...")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True, log_level="info")