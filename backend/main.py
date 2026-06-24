"""
Wiesel LTI 1.1 Backend
FastAPI app with LTI launch endpoint, chat API, and SQLite session management.
"""

import os
import json
import logging
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

# ============================================================================
# DATABASE SETUP
# ============================================================================

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SessionRecord(Base):
    """Session record from LTI launch"""
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
    """Chat message history"""
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    role = Column(String)  # "user" or "assistant"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# Create tables
Base.metadata.create_all(bind=engine)

# ============================================================================
# LTI 1.1 SIGNATURE VALIDATION
# ============================================================================


def _check_nonce(nonce: str) -> bool:
    """Return False if nonce was already used (replay attack)."""
    db = SessionLocal()
    try:
        return db.query(SessionRecord).filter(SessionRecord.nonce == nonce).first() is None
    finally:
        db.close()


def validate_lti_request(uri: str, params: dict, body: str = "") -> tuple[bool, str]:
    """
    Validate an LTI 1.1 OAuth 1.0a signed request.

    Returns (True, "") on success or (False, reason) on failure.
    In MOCK_LTI_MODE only the consumer key is checked – signature is skipped.
    """
    client_key = params.get("oauth_consumer_key", "")
    nonce      = params.get("oauth_nonce", "")
    timestamp  = params.get("oauth_timestamp", "0")

    # --- key check (always) ---
    if client_key != LTI_CONSUMER_KEY:
        return False, f"Unknown consumer key: {client_key!r}"

    if MOCK_LTI_MODE:
        logger.warning("MOCK_LTI_MODE active – skipping OAuth signature check")
        return True, ""

    # --- timestamp (±1 h) ---
    try:
        skew = abs(int(datetime.utcnow().timestamp()) - int(timestamp))
        if skew > 3600:
            return False, f"Timestamp skew too large: {skew}s"
    except ValueError:
        return False, "Invalid oauth_timestamp"

    # --- nonce replay ---
    if nonce and not _check_nonce(nonce):
        return False, f"Nonce already used: {nonce!r}"

    # --- HMAC-SHA1 signature ---
    collected = oauth_signature.collect_parameters(
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        exclude_oauth_signature=True,
        with_body=True,
    )
    # Merge URI params from the form POST
    collected += [(k, v) for k, v in params.items() if k != "oauth_signature"]

    base_string = oauth_signature.construct_base_string(
        "POST",
        oauth_signature.normalize_base_string_uri(uri),
        oauth_signature.normalize_parameters(collected),
    )
    expected = oauth_signature.sign_hmac_sha1(
        base_string,
        LTI_CONSUMER_SECRET,
        "",          # token_secret is empty for LTI 1.1
    )
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


class ChatResponse(BaseModel):
    response: str
    session_id: str
    timestamp: str


class WikiResponse(BaseModel):
    content: dict


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_db():
    """Dependency: get DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_jwt_token(session_id: str) -> str:
    """Create JWT token for session"""
    payload = {
        "session_id": session_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=8)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> Optional[dict]:
    """Verify JWT token"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except:
        return None


def load_knowledge_base() -> str:
    """Load Karpathy Wiki from wissen-basis.md (repo root). Falls back to Docker paths."""
    candidates = [
        Path(__file__).parent.parent / "knowledge_base" / "wissen-basis.md",  # local: wiesel/knowledge_base/wissen-basis.md
        Path("/knowledge_base/wissen-basis.md"),                                # Docker volume mount
        Path("/app/knowledge_base/wissen-basis.md"),                            # Docker /app
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return "# Wissensbasis nicht gefunden"


def build_system_prompt() -> str:
    """Load system prompt from system-prompt.md (repo root). Falls back to /system-prompt.md for Docker."""
    candidates = [
        Path(__file__).parent.parent / "system-prompt.md",  # local: wiesel/system-prompt.md
        Path("/system-prompt.md"),                           # Docker: mounted at repo root
        Path("/app/system-prompt.md"),                       # Docker alt
    ]
    for path in candidates:
        if path.exists():
            logger.info(f"Loading system prompt from {path}")
            return path.read_text(encoding="utf-8")
    logger.error("system-prompt.md not found in any candidate path")
    return "Du bist Wiesel, ein Studienbegleiter für WiSo-Erstsemester an der FAU Erlangen-Nürnberg."


async def call_claude(query: str, chat_history: list = None, kb_content: str = "") -> str:
    """Call Claude API with knowledge base context"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    # Build message history
    messages = []
    if chat_history:
        for msg in chat_history[-4:]:  # Keep last 4 messages for context
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
    
    # Current query
    messages.append({
        "role": "user",
        "content": f"{query}\n\n---\n**Verfügbare Wissensbasis:**\n{kb_content[:3000]}"  # Truncate KB
    })
    
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=build_system_prompt(),
            messages=messages
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return f"Entschuldigung, ich hatte einen technischen Fehler: {str(e)}"


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Wiesel Backend",
    description="LTI 1.1 Backend for Wiesel Chatbot (FAU WiSo)",
    version="0.1.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# ============================================================================
# ROUTES
# ============================================================================


@app.get("/")
async def root():
    """Health check"""
    return {"status": "ok", "service": "Wiesel Backend", "version": "0.1.0"}


@app.get("/chat")
async def chat_page(request: Request, debug: bool = False):
    """Serve the chat widget.
    ?debug=true  → creates a test session without LTI and redirects with token.
    ?token=...   → normal flow after LTI launch or debug redirect.
    """
    if debug:
        db = SessionLocal()
        try:
            # Stable session_id – not time-dependent, so DB lookup always works
            # and chat_messages accumulate across debug visits
            debug_session_id = "debug_session_wiesel"
            token = jwt.encode(
                {"user": "debug_user", "session_id": debug_session_id, "debug": True},
                JWT_SECRET
            )
            debug_session = SessionRecord(
                id=debug_session_id,
                user_id="debug_user",
                course_id="debug_course",
                user_role="Learner",
                user_name="Debug Student",
                course_name="Debug Mode – kein StudOn",
                nonce=None,
                created_at=datetime.utcnow(),
            )
            db.merge(debug_session)
            db.commit()
            logger.info("Debug session upserted – session_id=debug_session_wiesel, user_id=debug_user")
        finally:
            db.close()
        from urllib.parse import quote
        token_enc = quote(token, safe="")
        return RedirectResponse(
            url=f"/chat?token={token_enc}&session_id={debug_session_id}",
            status_code=302
        )
    return FileResponse(str(_static_dir / "chat.html"))


@app.post("/lti/launch")
async def lti_launch(request: Request):
    """
    LTI 1.1 Launch Endpoint
    Receives POST from StudOn, validates OAuth 1.0a signature, creates session
    """
    db = SessionLocal()
    
    try:
        # Read body ONCE – request.body() and request.form() share the same
        # stream; calling both without caching causes "Stream consumed" errors.
        raw_body = await request.body()
        body = raw_body.decode("utf-8")

        # Parse form data from the cached body string
        from urllib.parse import parse_qs, unquote_plus
        parsed = parse_qs(body, keep_blank_values=True)
        form_data = {k: v[0] for k, v in parsed.items()}

        logger.info(f"LTI Launch received. Keys: {list(form_data.keys())[:5]}")

        # Validate OAuth 1.0a signature (skipped in MOCK_LTI_MODE)
        params = form_data
        uri = str(request.url)
        valid, reason = validate_lti_request(uri, params, body)
        if not valid:
            logger.error(f"LTI validation failed: {reason}")
            return JSONResponse({"error": "LTI validation failed", "detail": reason}, status_code=401)

        # Extract LTI context
        user_id = form_data.get("user_id", "anonymous")
        course_id = form_data.get("course_id", "unknown")
        roles = form_data.get("roles", "Learner")
        user_name = form_data.get("lis_person_name_full", "Student")
        course_name = form_data.get("context_title", "Unknown Course")
        nonce = form_data.get("oauth_nonce", None)
        
        # Create session record
        session_id = jwt.encode(
            {"user": user_id, "ts": datetime.utcnow().timestamp()},
            JWT_SECRET
        )
        
        session_record = SessionRecord(
            id=session_id,
            user_id=user_id,
            course_id=course_id,
            user_role=roles.split(",")[0] if roles else "student",
            user_name=user_name,
            course_name=course_name,
            nonce=nonce
        )
        db.add(session_record)
        db.commit()
        
        logger.info(f"LTI session created: {session_id} for user {user_id}")
        
        # Create JWT token for frontend
        token = create_jwt_token(session_id)
        
        # Redirect to frontend (will be iframe URL)
        # TODO: update to actual frontend URL
        return RedirectResponse(
            url=f"/chat?token={token}&session_id={session_id}&user={user_name}&course={course_name}",
            status_code=302
        )
    
    except Exception as e:
        logger.error(f"LTI Launch error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)
    
    finally:
        db.close()


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Chat API
    Takes query + session_id, returns Claude response
    """
    db = SessionLocal()
    
    try:
        # Validate session
        session = db.query(SessionRecord).filter(SessionRecord.id == request.session_id).first()
        if not session:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        # Update last accessed
        session.last_accessed = datetime.utcnow()
        db.commit()
        
        # Get chat history
        history = db.query(ChatMessage).filter(
            ChatMessage.session_id == request.session_id
        ).order_by(ChatMessage.created_at).all()
        
        chat_history = [{"role": msg.role, "content": msg.content} for msg in history]
        
        # Load knowledge base
        kb_content = load_knowledge_base()
        
        # Call Claude
        response = await call_claude(request.query, chat_history, kb_content)
        
        # Store messages in DB
        user_msg = ChatMessage(
            session_id=request.session_id,
            role="user",
            content=request.query
        )
        assistant_msg = ChatMessage(
            session_id=request.session_id,
            role="assistant",
            content=response
        )
        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()
        
        return ChatResponse(
            response=response,
            session_id=request.session_id,
            timestamp=datetime.utcnow().isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        db.close()


@app.get("/api/wiki")
async def wiki_endpoint():
    """
    Wiki API
    Returns Karpathy Wiki as JSON for frontend
    """
    try:
        content = load_knowledge_base()
        return {
            "content": content,
            "format": "markdown",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Wiki error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/session/{session_id}")
async def session_endpoint(session_id: str):
    """
    Get session metadata
    """
    db = SessionLocal()
    
    try:
        session = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "session_id": session.id,
            "user_id": session.user_id,
            "user_name": session.user_name,
            "course_id": session.course_id,
            "course_name": session.course_name,
            "user_role": session.user_role,
            "created_at": session.created_at.isoformat(),
            "last_accessed": session.last_accessed.isoformat()
        }
    finally:
        db.close()


@app.get("/health")
async def health_check():
    """Health check for deployment"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "db": "connected"
    }


# ============================================================================
# STARTUP / SHUTDOWN
# ============================================================================


# ============================================================================
# LOGS API
# ============================================================================

@app.get("/api/logs/daily")
async def get_daily_logs(date: Optional[str] = None):
    """Return all chat messages for a given day (default: today) as JSON."""
    db = SessionLocal()
    try:
        if date:
            try:
                target = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
        else:
            target = datetime.utcnow().date()

        day_start = datetime(target.year, target.month, target.day, 0, 0, 0)
        day_end   = datetime(target.year, target.month, target.day, 23, 59, 59)

        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.created_at >= day_start, ChatMessage.created_at <= day_end)
            .order_by(ChatMessage.created_at)
            .all()
        )

        # Group by session
        sessions: dict = {}
        for m in messages:
            if m.session_id not in sessions:
                sessions[m.session_id] = []
            sessions[m.session_id].append({
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            })

        return {
            "date": target.isoformat(),
            "total_messages": len(messages),
            "total_sessions": len(sessions),
            "sessions": sessions,
        }
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


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
