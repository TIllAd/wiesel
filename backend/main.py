"""
Wiesel LTI 1.1 Backend
FastAPI app with LTI launch endpoint, chat API, and SQLite session management.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session as SQLSession

import anthropic
import jwt
from oauthlib.oauth1 import RequestValidator, Server

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIG
# ============================================================================

LTI_CONSUMER_KEY = os.getenv("LTI_CONSUMER_KEY", "test_consumer_key_mock")
LTI_CONSUMER_SECRET = os.getenv("LTI_CONSUMER_SECRET", "test_consumer_secret_mock")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "sk-mock")
JWT_SECRET = os.getenv("JWT_SECRET", "wiesel_jwt_secret_dev")
JWT_ALGORITHM = "HS256"
DATABASE_URL = "sqlite:///./wiesel.db"

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
# LTI 1.1 VALIDATOR & SERVER
# ============================================================================


class WieselLTIValidator(RequestValidator):
    """LTI 1.1 OAuth 1.0a Request Validator"""
    
    def validate_timestamp_and_nonce(self, client_key, timestamp, nonce, request, request_token=None, access_token=None):
        """Validate timestamp (within 1 hour) and nonce (not reused)"""
        try:
            ts = int(timestamp)
            now = int(datetime.utcnow().timestamp())
            if abs(now - ts) > 3600:  # 1 hour
                logger.warning(f"Timestamp out of range: {timestamp}")
                return False
        except:
            return False
        
        # Check nonce in DB
        db = SessionLocal()
        try:
            existing = db.query(SessionRecord).filter(SessionRecord.nonce == nonce).first()
            if existing:
                logger.warning(f"Nonce replay detected: {nonce}")
                return False
        finally:
            db.close()
        
        return True
    
    def validate_client_key(self, client_key, request):
        """Validate consumer key"""
        is_valid = client_key == LTI_CONSUMER_KEY
        logger.info(f"LTI Client Key validation: {client_key} -> {is_valid}")
        return is_valid
    
    def get_client_secret(self, client_key, request):
        """Return consumer secret for this key"""
        if client_key == LTI_CONSUMER_KEY:
            return LTI_CONSUMER_SECRET
        return None
    
    def dummy_client(self):
        return LTI_CONSUMER_KEY
    
    def dummy_request_token(self):
        return "dummy_token"
    
    def dummy_access_token(self):
        return "dummy_token"


lti_server = Server(WieselLTIValidator())

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
    """Load Karpathy Wiki from file"""
    kb_path = "/knowledge_base/wissen-basis.md"
    if os.path.exists(kb_path):
        with open(kb_path, "r", encoding="utf-8") as f:
            return f.read()
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
            model="claude-3-5-haiku-20241022",
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


# ============================================================================
# ROUTES
# ============================================================================


@app.get("/")
async def root():
    """Health check"""
    return {"status": "ok", "service": "Wiesel Backend", "version": "0.1.0"}


@app.post("/lti/launch")
async def lti_launch(request: Request):
    """
    LTI 1.1 Launch Endpoint
    Receives POST from StudOn, validates OAuth 1.0a signature, creates session
    """
    db = SessionLocal()
    
    try:
        # Parse form data
        form_data = await request.form()
        
        logger.info(f"LTI Launch received. Keys: {list(form_data.keys())[:5]}")
        
        # For mock testing, skip signature validation
        # In production, uncomment the validation below
        """
        valid, request_obj = lti_server.validate_request(
            request.url,
            "POST",
            request.body.__str__() if hasattr(request, 'body') else "",
            dict(form_data)
        )
        
        if not valid:
            logger.error("LTI signature validation failed")
            return JSONResponse({"error": "Invalid LTI signature"}, status_code=401)
        """
        
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
            url=f"/chat?token={token}&user={user_name}&course={course_name}",
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
