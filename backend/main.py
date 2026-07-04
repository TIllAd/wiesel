"""
Wiesel LTI 1.1 Backend
FastAPI app with LTI launch endpoint, chat API, and SQLite session management.
"""

import os
import json
import logging
import re
import time
import uuid
import base64
import binascii
from collections import defaultdict, deque
from io import BytesIO
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from pydantic import BaseModel
from PIL import Image, UnidentifiedImageError
from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session as SQLSession

import anthropic
import jwt
import hmac as hmac_lib
from oauthlib.oauth1.rfc5849 import signature as oauth_signature

APP_TIMEZONE = ZoneInfo("Europe/Berlin")


def utc_naive_to_app_time(value: datetime) -> datetime:
    """Convert DB timestamps stored as naive UTC to timezone-aware Europe/Berlin time."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(APP_TIMEZONE)


def app_time_to_utc_naive(value: datetime) -> datetime:
    """Convert timezone-aware/local app time to naive UTC for existing DB columns."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=APP_TIMEZONE)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def json_timestamp(value: datetime) -> str:
    """Serialize DB timestamps for API responses in the app timezone."""
    # DB writes stay naive UTC via datetime.utcnow(); JSON responses always expose app time here.
    return utc_naive_to_app_time(value).isoformat()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Wiesel Backend", description="LTI 1.1 Backend for Wiesel Chatbot (FAU WiSo)", version="0.1.0")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled server error", exc_info=True)
    return JSONResponse({"detail": "Etwas ist schiefgelaufen. Versuch es nochmal."}, status_code=500)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in {400, 413, 429}:
        detail = exc.detail
    else:
        if exc.status_code >= 500:
            logger.error("HTTP server error", exc_info=True)
        detail = "Etwas ist schiefgelaufen. Versuch es nochmal."
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)

# ============================================================================
# CONFIG
# ============================================================================

LTI_CONSUMER_KEY = os.getenv("LTI_CONSUMER_KEY", "test_consumer_key_mock")
LTI_CONSUMER_SECRET = os.getenv("LTI_CONSUMER_SECRET", "test_consumer_secret_mock")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
JWT_SECRET = os.getenv("JWT_SECRET", "wiesel_jwt_secret_dev")
JWT_ALGORITHM = "HS256"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./wiesel.db")
MOCK_LTI_MODE = os.getenv("MOCK_LTI_MODE", "true").lower() == "true"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
DEFAULT_GREETING = "Hey, ich bin Weasel, dein Uni-Buddy – ich begleite dich durch deinen Unistart. Wie kann ich dir helfen?"
SYSTEM_PROMPT_LEAK_FALLBACK = "Komm zum Punkt – was willst du über die WiSo wissen?"
TECHNICAL_ERROR_FALLBACK = "Gerade klemmt die Technik im Hintergrund. Versuch es bitte gleich nochmal."
AMBIGUOUS_FIRST_MESSAGE_FALLBACK = "{message}? Damit kann ich allein nichts anfangen. Gib mir bitte kurz mehr Kontext – zum Beispiel: Prüfungen, StudOn, Stundenplan, BAföG oder Studienstart."
LLM_HEALTH = {"ok": bool(ANTHROPIC_API_KEY), "last_success": None, "last_error": None}
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(3 * 1024 * 1024)))
MAX_IMAGE_DIMENSION = int(os.getenv("MAX_IMAGE_DIMENSION", "1600"))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", str(MAX_IMAGE_DIMENSION * MAX_IMAGE_DIMENSION)))
MAX_CHAT_REQUEST_BYTES = int(os.getenv("MAX_CHAT_REQUEST_BYTES", str(5 * 1024 * 1024)))
MAX_QUERY_CHARS_HARD = int(os.getenv("MAX_QUERY_CHARS_HARD", "3000"))
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

# USD pro 1 Mio Tokens. Defaults reflect Claude Haiku 4.5 public pricing:
# base input 1.00, 5m cache write 1.25, cache hits/refreshes 0.10, output 5.00.
# Configurable because model pricing changes more often than documentation survives.
# (A familiar little tragedy.)
USD_PER_EUR = float(os.getenv("USD_PER_EUR", "1.08"))
LLM_INPUT_USD_PER_MTOK = float(os.getenv("LLM_INPUT_USD_PER_MTOK", "1.00"))
LLM_OUTPUT_USD_PER_MTOK = float(os.getenv("LLM_OUTPUT_USD_PER_MTOK", "5.00"))
LLM_CACHE_WRITE_USD_PER_MTOK = float(os.getenv("LLM_CACHE_WRITE_USD_PER_MTOK", "1.25"))
LLM_CACHE_READ_USD_PER_MTOK = float(os.getenv("LLM_CACHE_READ_USD_PER_MTOK", "0.10"))

# ============================================================================
# SECURITY / OPS CONFIG (P0)
# ============================================================================

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "https://wiesel.chatbot-wiso.de").split(",") if o.strip()]
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "700"))
JWT_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "2"))
DAILY_BUDGET_EUR = float(os.getenv("DAILY_BUDGET_EUR", "15"))
RATE_LIMIT_CHAT_PER_MIN_SESSION = int(os.getenv("RATE_LIMIT_CHAT_PER_MIN_SESSION", "10"))
RATE_LIMIT_CHAT_PER_MIN_IP = int(os.getenv("RATE_LIMIT_CHAT_PER_MIN_IP", "30"))
RATE_LIMIT_DEBUG_SESSIONS_PER_DAY_IP = int(os.getenv("RATE_LIMIT_DEBUG_SESSIONS_PER_DAY_IP", "20"))
BUDGET_EXCEEDED_FALLBACK = "Wiesel macht gerade eine Zwangspause (Tagesbudget erreicht). Versuch es bitte morgen wieder — oder schreib ans Studienbüro: studienbuero@wiso.fau.de."
RATE_LIMITED_DETAIL = "Langsam — zu viele Anfragen. Warte kurz und versuch es dann nochmal."

# ── Cloudflare Access (zweite Auth-Methode für Admin-Endpoints) ─────────────
# Team-Domain: "wiso-team" oder "wiso-team.cloudflareaccess.com" (ohne https://).
# Audience-Tag: aus der Access-Application in Cloudflare Zero Trust kopieren.
# Beide gesetzt → Cf-Access-Jwt-Assertion-Header wird als Admin-Auth akzeptiert.
CF_ACCESS_TEAM_DOMAIN = os.getenv("CF_ACCESS_TEAM_DOMAIN", "").strip()
CF_ACCESS_AUD = os.getenv("CF_ACCESS_AUD", "").strip()


def _cf_access_issuer() -> str:
    domain = CF_ACCESS_TEAM_DOMAIN
    if not domain:
        return ""
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain.rstrip("/")
    if "." not in domain:
        domain = f"{domain}.cloudflareaccess.com"
    return f"https://{domain}"


_DEV_JWT_SECRETS = {"wiesel_jwt_secret_dev", ""}
_DEV_LTI_SECRETS = {"test_consumer_secret_mock", ""}


def validate_config() -> None:
    """Fail fast in production when secrets are missing or left on dev defaults."""
    problems = []
    if ENVIRONMENT == "production":
        if not ANTHROPIC_API_KEY:
            problems.append("ANTHROPIC_API_KEY fehlt")
        if JWT_SECRET in _DEV_JWT_SECRETS:
            problems.append("JWT_SECRET fehlt oder steht auf Dev-Default")
        if not MOCK_LTI_MODE and LTI_CONSUMER_SECRET in _DEV_LTI_SECRETS:
            problems.append("LTI_CONSUMER_SECRET fehlt oder steht auf Dev-Default")
        if not ADMIN_API_KEY:
            problems.append("ADMIN_API_KEY fehlt (Log-/Analytics-Endpoints brauchen ihn)")
    if problems:
        raise RuntimeError("Unsichere Konfiguration in production: " + "; ".join(problems))
    if MOCK_LTI_MODE:
        # Bewusst kein Hard-Fail: Default-Umstellung auf false erst NACH einem
        # verifizierten echten StudOn-Launch (Fix-Plan Phase 1, Schritt 1 → 2).
        logger.critical("MOCK_LTI_MODE ist AKTIV — OAuth-Signaturen werden NICHT geprüft. Nur für Test/Debug akzeptabel.")


validate_config()

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


class LTINonce(Base):
    """Consumed OAuth nonces. Stored independently of sessions so a failed
    launch cannot be replayed and successful nonces survive session cleanup."""
    __tablename__ = "lti_nonces"
    nonce = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    model = Column(String, index=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_creation_input_tokens = Column(Integer, default=0)
    cache_read_input_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    estimated_cost_eur = Column(Float, default=0.0)
    latency_ms = Column(Integer, nullable=True)
    error_type = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


Base.metadata.create_all(bind=engine)

# ============================================================================
# LTI 1.1 SIGNATURE VALIDATION
# ============================================================================

def _nonce_already_used(nonce: str) -> bool:
    db = SessionLocal()
    try:
        return db.query(LTINonce).filter(LTINonce.nonce == nonce).first() is not None
    finally:
        db.close()


def _consume_nonce(nonce: str) -> None:
    """Persist a nonce after successful validation; prune entries older than the
    timestamp window (they can no longer pass the skew check anyway)."""
    db = SessionLocal()
    try:
        db.add(LTINonce(nonce=nonce))
        db.query(LTINonce).filter(
            LTINonce.created_at < datetime.utcnow() - timedelta(hours=2)
        ).delete()
        db.commit()
    except Exception:
        db.rollback()
        logger.error("Could not persist LTI nonce", exc_info=True)
    finally:
        db.close()


def validate_lti_request(uri: str, params: dict, body: str = "") -> tuple[bool, str]:
    """LTI 1.1 OAuth 1.0a validation (HMAC-SHA1).

    Fix 2026-07: the previous version collected the body parameters via
    collect_parameters() AND re-added `params` afterwards, so every parameter
    appeared twice in the signature base string — legitimate launches could
    never validate. The base string is now built from the form body exactly
    once (plus any query-string parameters), per RFC 5849 §3.4.1.3.
    """
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

    if not nonce:
        return False, "Missing oauth_nonce"
    if _nonce_already_used(nonce):
        return False, f"Nonce already used: {nonce!r}"

    collected = oauth_signature.collect_parameters(
        uri_query=urlparse(uri).query,
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        exclude_oauth_signature=True,
        with_realm=False,
    )

    base_string = oauth_signature.construct_base_string(
        "POST",
        oauth_signature.normalize_base_string_uri(uri),
        oauth_signature.normalize_parameters(collected),
    )
    expected = oauth_signature.sign_hmac_sha1(base_string, LTI_CONSUMER_SECRET, "")
    received = params.get("oauth_signature", "")
    if not hmac_lib.compare_digest(expected, received):
        return False, "OAuth signature mismatch"

    _consume_nonce(nonce)
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


ADMIN_COOKIE_NAME = "wiesel_admin_key"

# JWKS-Client lazy + einmal pro Prozess; PyJWKClient cacht die Keys intern.
_cf_jwks_client = None


def _get_cf_jwks_client():
    global _cf_jwks_client
    if _cf_jwks_client is None:
        from jwt import PyJWKClient
        _cf_jwks_client = PyJWKClient(f"{_cf_access_issuer()}/cdn-cgi/access/certs", cache_keys=True)
    return _cf_jwks_client


def verify_cf_access_jwt(token: str) -> bool:
    """Verify a Cloudflare Access `Cf-Access-Jwt-Assertion` header against the
    team's public JWKS. Signature, exp, audience (Access-Application) und
    issuer (Team-Domain) werden geprüft — ein gefälschter Header ohne gültiges
    Access-Login scheitert also auch dann, wenn er den Origin direkt erreicht."""
    if not (CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD and token):
        return False
    try:
        signing_key = _get_cf_jwks_client().get_signing_key_from_jwt(token)
        jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=CF_ACCESS_AUD,
            issuer=_cf_access_issuer(),
            options={"require": ["exp", "aud", "iss"]},
        )
        return True
    except Exception as e:
        logger.warning(f"Cloudflare Access JWT rejected: {e.__class__.__name__}: {e}")
        return False


def _mint_admin_cookie() -> str:
    """Kurzlebiges, signiertes Admin-Session-Token fürs Cookie. Bewusst NICHT
    der rohe ADMIN_API_KEY: der Auto-Mint über Cloudflare Access würde den
    echten Key sonst auf jeden Team-Browser verteilen, und jede Key-Rotation
    würde alle Cookies gleich mit betreffen."""
    return jwt.encode(
        {"scope": "admin", "iat": datetime.utcnow(), "exp": datetime.utcnow() + timedelta(hours=8)},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def _admin_cookie_valid(value: str) -> bool:
    if not value:
        return False
    # Übergangsweise: alte Cookies aus dem manuellen ?key=-Bootstrap enthielten
    # den rohen Key — bleiben bis zu ihrem Ablauf gültig.
    if ADMIN_API_KEY and hmac_lib.compare_digest(value.encode(), ADMIN_API_KEY.encode()):
        return True
    try:
        claims = jwt.decode(value, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return claims.get("scope") == "admin"
    except Exception:
        return False


def _admin_auth_method(request: Request) -> Optional[str]:
    """Welcher Auth-Weg trägt diesen Request? 'cf' | 'key' | 'cookie' | None."""
    cf_token = request.headers.get("cf-access-jwt-assertion", "")
    if cf_token and verify_cf_access_jwt(cf_token):
        return "cf"
    if ADMIN_API_KEY:
        header_key = request.headers.get("x-admin-key") or ""
        if header_key and hmac_lib.compare_digest(header_key.encode(), ADMIN_API_KEY.encode()):
            return "key"
    if _admin_cookie_valid(request.cookies.get(ADMIN_COOKIE_NAME) or ""):
        return "cookie"
    return None


def _set_admin_cookie(response) -> None:
    response.set_cookie(
        ADMIN_COOKIE_NAME, _mint_admin_cookie(),
        httponly=True, samesite="lax",
        secure=(ENVIRONMENT == "production"),
        max_age=8 * 3600,
    )


def _raise_admin_unauthorized() -> None:
    cf_configured = bool(CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD)
    if not ADMIN_API_KEY and not cf_configured:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    raise HTTPException(status_code=401, detail="Invalid admin credentials")


def require_admin(request: Request) -> None:
    """Guard for log/analytics/report endpoints and internal docs.

    Drei Auth-Wege:
    1. Cloudflare Access: gültiges `Cf-Access-Jwt-Assertion`-JWT (nur auf
       /internal/* vorhanden — die Access-Application ist darauf begrenzt).
    2. ADMIN_API_KEY via X-Admin-Key-Header (Scripts, Tests, Fable).
    3. HttpOnly-Admin-Cookie — signiertes Session-Token, gesetzt entweder
       manuell über /internal/?key=<key> oder automatisch beim ersten
       CF-verifizierten /internal/*-Aufruf (deckt die /api/*-Fetches der
       Dashboards ab, die Cloudflare Access selbst nicht schützt).
    Ist kein Weg konfiguriert, sind die Endpoints gesperrt (503).
    """
    if _admin_auth_method(request) is None:
        _raise_admin_unauthorized()


# ── Rate limiting (in-memory sliding window; per process) ───────────────────
_rate_buckets: dict[str, deque] = defaultdict(deque)


def rate_limit_exceeded(key: str, limit: int, window_seconds: float = 60.0) -> bool:
    now = time.monotonic()
    bucket = _rate_buckets[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Daily budget kill-switch ────────────────────────────────────────────────
def todays_llm_cost_eur() -> float:
    from sqlalchemy import func
    day_start_app = datetime.now(APP_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = app_time_to_utc_naive(day_start_app)
    db = SessionLocal()
    try:
        total = db.query(func.coalesce(func.sum(LLMUsage.estimated_cost_eur), 0.0)).filter(
            LLMUsage.created_at >= day_start_utc
        ).scalar()
        return float(total or 0.0)
    finally:
        db.close()


def budget_exhausted() -> bool:
    if DAILY_BUDGET_EUR <= 0:
        return False
    try:
        spent = todays_llm_cost_eur()
    except Exception:
        logger.error("Budget check failed", exc_info=True)
        return False
    if spent >= DAILY_BUDGET_EUR:
        logger.critical(f"Tagesbudget erreicht: {spent:.2f} EUR >= {DAILY_BUDGET_EUR:.2f} EUR — LLM-Calls pausiert bis Mitternacht.")
        return True
    return False


from backend.routers import agenda as agenda_router
from backend.routers import mentor as mentor_router
agenda_router.init(Base, get_db, json_timestamp, engine)
mentor_router.init(Base, get_db, json_timestamp, engine)
app.include_router(agenda_router.router)
app.include_router(mentor_router.router)


def create_jwt_token(session_id: str) -> str:
    payload = {
        "session_id": session_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_TTL_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except:
        return None


def _strip_data_url(image_base64: str) -> tuple[str, Optional[str]]:
    """Return raw base64 payload and optional MIME type from a data URL."""
    if not image_base64:
        return "", None
    if image_base64.startswith("data:") and ";base64," in image_base64:
        header, payload = image_base64.split(",", 1)
        mime = header[5:].split(";", 1)[0].lower()
        return payload, mime
    return image_base64, None


def _detect_mime_from_bytes(image_bytes: bytes) -> Optional[str]:
    if image_bytes[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if image_bytes[:8] == bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]):
        return "image/png"
    if image_bytes[:12].startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


def _detect_mime(b64: str, fallback: str = "image/jpeg") -> str:
    try:
        payload, data_url_mime = _strip_data_url(b64)
        header = base64.b64decode(payload[:32], validate=True)
        return _detect_mime_from_bytes(header) or data_url_mime or fallback
    except Exception:
        pass
    return fallback


def validate_image_base64(image_base64: str, requested_mime: str = "image/jpeg") -> tuple[str, str]:
    """Validate and normalize an uploaded image before it reaches the LLM API."""
    payload, data_url_mime = _strip_data_url(image_base64)
    if not payload:
        raise HTTPException(status_code=400, detail="Bilddaten fehlen.")

    # Base64 expands binary by ~4/3. This pre-check rejects absurd request bodies
    # before decoding them into memory. Yes, even the obvious guard deserves to exist.
    max_base64_chars = ((MAX_IMAGE_BYTES + 2) // 3) * 4
    if len(payload) > max_base64_chars + 4096:
        raise HTTPException(status_code=413, detail=f"Bild ist zu groß. Maximum: {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")

    try:
        image_bytes = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Ungültige Bilddaten.")

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"Bild ist zu groß. Maximum: {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")

    detected_mime = _detect_mime_from_bytes(image_bytes)
    requested_mime = (requested_mime or data_url_mime or "").lower()
    if detected_mime not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Nur JPG, PNG oder WebP sind erlaubt.")

    if requested_mime and requested_mime not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Nur JPG, PNG oder WebP sind erlaubt.")

    try:
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
            if width <= 0 or height <= 0 or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION or width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail=f"Bildauflösung ist zu groß. Maximum: {MAX_IMAGE_DIMENSION}×{MAX_IMAGE_DIMENSION} px.")
            img.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="Ungültige Bilddatei.")

    return payload, detected_mime


_kb_cache: dict = {"signature": None, "content": None}


def load_knowledge_base() -> str:
    """Concatenate all KB markdown files. Cached in memory and invalidated via
    file mtimes, instead of re-reading ~60 files on every chat request."""
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

    md_files = sorted(kb_dir.glob("**/*.md"), key=lambda p: str(p))
    try:
        signature = tuple((str(p), p.stat().st_mtime_ns) for p in md_files)
    except OSError:
        signature = None
    if signature is not None and signature == _kb_cache["signature"] and _kb_cache["content"]:
        return _kb_cache["content"]

    parts = []
    main_kb = kb_dir / "wissen-basis.md"
    if main_kb.exists():
        parts.append(main_kb.read_text(encoding="utf-8"))

    for md_file in md_files:
        if md_file.name == "wissen-basis.md":
            continue
        try:
            parts.append(md_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"KB skip {md_file.name}: {e}")

    content = "\n\n---\n\n".join(parts) if parts else "# Wissensbasis nicht gefunden"
    _kb_cache.update({"signature": signature, "content": content})
    logger.info(f"KB (re)loaded: {len(md_files)} Dateien, {len(content)} Zeichen")
    return content


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


_STATIC_LEAK_MARKERS = [
    "Wiesel – System-Prompt",
    "Wiesel - System-Prompt",
    "Offen · Charakter-First",   # legacy prompt versions
    "## Wie ich bin",
    "## Was ich weiß",
    "## Faktenbasis",
]
_leak_marker_cache: dict = {"mtime": None, "markers": _STATIC_LEAK_MARKERS}


def _leak_markers() -> list[str]:
    """Static markers + all `## ` section headers of the *current* prompt file,
    so the detector follows prompt versions instead of matching stale headers."""
    candidates = [
        Path(__file__).parent.parent / "system-prompt.md",
        Path("/system-prompt.md"),
        Path("/app/system-prompt.md"),
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        return _STATIC_LEAK_MARKERS
    try:
        mtime = path.stat().st_mtime_ns
        if mtime != _leak_marker_cache["mtime"]:
            headers = [
                line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("## ")
            ]
            _leak_marker_cache.update({"mtime": mtime, "markers": _STATIC_LEAK_MARKERS + headers})
    except OSError:
        pass
    return _leak_marker_cache["markers"]


def looks_like_system_prompt_leak(text: str) -> bool:
    """Detect accidental raw prompt disclosure before it reaches the frontend."""
    if not text:
        return False
    return any(marker in text for marker in _leak_markers())


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


def estimate_llm_cost_usd(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    return (
        input_tokens * LLM_INPUT_USD_PER_MTOK
        + output_tokens * LLM_OUTPUT_USD_PER_MTOK
        + cache_creation_input_tokens * LLM_CACHE_WRITE_USD_PER_MTOK
        + cache_read_input_tokens * LLM_CACHE_READ_USD_PER_MTOK
    ) / 1_000_000


def record_llm_usage(
    session_id: str,
    model: str,
    usage=None,
    latency_ms: int | None = None,
    error_type: str | None = None,
) -> None:
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cache_creation_input_tokens = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cache_read_input_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    estimated_cost_usd = estimate_llm_cost_usd(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )
    db = SessionLocal()
    try:
        db.add(LLMUsage(
            session_id=session_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            estimated_cost_usd=estimated_cost_usd,
            estimated_cost_eur=estimated_cost_usd / USD_PER_EUR if USD_PER_EUR else estimated_cost_usd,
            latency_ms=latency_ms,
            error_type=error_type,
        ))
        db.commit()
    except Exception:
        logger.error("Could not record LLM usage", exc_info=True)
        db.rollback()
    finally:
        db.close()


# Ein Client für den Prozess. Async, damit ein 3–5-s-LLM-Call nicht den
# ganzen Event-Loop blockiert (vorher wurden parallele Nutzer seriell bedient).
_anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


async def call_claude(session_id: str, query: str, chat_history: list = None, kb_content: str = "", image_base64: str = None, image_type: str = "image/jpeg") -> str:
    if _anthropic_client is None:
        logger.error("ANTHROPIC_API_KEY fehlt — kein LLM-Call möglich")
        return TECHNICAL_ERROR_FALLBACK
    client = _anthropic_client

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
        started_at = datetime.utcnow()
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            system=system_blocks,
            messages=messages,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        )
        latency_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        record_llm_usage(session_id=session_id, model=ANTHROPIC_MODEL, usage=response.usage, latency_ms=latency_ms)
        logger.info(f"LLM usage: input={response.usage.input_tokens} | output={response.usage.output_tokens} | cache_read={getattr(response.usage, 'cache_read_input_tokens', 0)} | cache_write={getattr(response.usage, 'cache_creation_input_tokens', 0)} | latency_ms={latency_ms} | stop={response.stop_reason}")
        text = response.content[0].text
        if response.stop_reason == "max_tokens":
            # Nicht mitten im Satz enden lassen: letzten vollständigen Satz behalten.
            logger.warning("LLM-Antwort lief in max_tokens — wird sauber gekürzt")
            cut = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
            if cut > 40:
                text = text[: cut + 1]
            text += "\n\n*(Antwort gekürzt — frag nach, dann mache ich kompakt weiter.)*"
        if looks_like_system_prompt_leak(text):
            logger.error("Blocked likely system-prompt leak in Claude response")
            return SYSTEM_PROMPT_LEAK_FALLBACK
        LLM_HEALTH.update({"ok": True, "last_success": json_timestamp(datetime.utcnow()), "last_error": None})
        return text
    except Exception as e:
        logger.error("Claude API error", exc_info=True)
        record_llm_usage(session_id=session_id, model=ANTHROPIC_MODEL, error_type=e.__class__.__name__)
        LLM_HEALTH.update({"ok": False, "last_error": json_timestamp(datetime.utcnow())})
        return TECHNICAL_ERROR_FALLBACK


# ============================================================================
# FASTAPI APP
# ============================================================================

@app.middleware("http")
async def block_internal_docs_on_open_mounts(request: Request, call_next):
    """docs/internal ist NICHT mehr über die offenen StaticFiles-Mounts erreichbar.
    Kanonischer (geschützter) Zugang: /internal/... — siehe internal_docs()."""
    path = unquote(request.url.path).replace("\\", "/").lower()
    while "//" in path:
        path = path.replace("//", "/")
    if path.startswith("/static/docs/internal"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return await call_next(request)


@app.middleware("http")
async def reject_oversized_chat_requests(request: Request, call_next):
    if request.url.path == "/api/chat":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > MAX_CHAT_REQUEST_BYTES
            except ValueError:
                too_large = False
            if too_large:
                return JSONResponse(
                    {"detail": f"Request ist zu groß. Maximum: {MAX_CHAT_REQUEST_BYTES // (1024 * 1024)} MB."},
                    status_code=413,
                )
    return await call_next(request)


# CORS: same-origin deployment braucht eigentlich gar kein CORS; erlaubt sind
# nur die konfigurierten Origins. allow_credentials=False, weil Auth über
# explizite Header/Token läuft, nicht über Cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Key"],
)

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# ============================================================================
# ROUTES
# ============================================================================

@app.get("/")
async def docs_landing_page():
    docs_index = _static_dir / "docs" / "index.html"
    if docs_index.exists():
        return FileResponse(str(docs_index))
    return RedirectResponse(url="/chat?debug=true")


@app.get("/chat")
async def chat_page(request: Request, debug: str | None = None):
    # Only the explicit entry URL /chat?debug=true should mint a fresh debug
    # session. The rendered chat page uses debug=1 only as a frontend marker;
    # treating every truthy debug value as a launch request causes an infinite
    # redirect loop: debug=true -> debug=1 -> new token -> debug=1 -> ...
    if debug == "true":
        if rate_limit_exceeded(f"debugsess:ip:{client_ip(request)}", RATE_LIMIT_DEBUG_SESSIONS_PER_DAY_IP, window_seconds=86400.0):
            raise HTTPException(status_code=429, detail=RATE_LIMITED_DETAIL)
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
    except Exception:
        logger.error("LTI Launch error", exc_info=True)
        raise HTTPException(status_code=500)
    finally:
        db.close()


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, http_request: Request):
    db = SessionLocal()
    try:
        if len(request.query or "") > MAX_QUERY_CHARS_HARD:
            raise HTTPException(status_code=400, detail=f"Deine Nachricht ist zu lang. Kürz sie bitte auf maximal {MAX_QUERY_CHARS_HARD} Zeichen.")

        if rate_limit_exceeded(f"chat:sess:{request.session_id}", RATE_LIMIT_CHAT_PER_MIN_SESSION):
            raise HTTPException(status_code=429, detail=RATE_LIMITED_DETAIL)
        if rate_limit_exceeded(f"chat:ip:{client_ip(http_request)}", RATE_LIMIT_CHAT_PER_MIN_IP):
            raise HTTPException(status_code=429, detail=RATE_LIMITED_DETAIL)

        session = db.query(SessionRecord).filter(SessionRecord.id == request.session_id).first()
        if not session:
            raise HTTPException(status_code=401, detail="Invalid session")

        session.last_accessed = datetime.utcnow()
        db.commit()

        if request.query == "__greeting__" and not request.image_base64:
            return ChatResponse(response=DEFAULT_GREETING, session_id=request.session_id, timestamp=json_timestamp(datetime.utcnow()))

        history = db.query(ChatMessage).filter(ChatMessage.session_id == request.session_id).order_by(ChatMessage.created_at).all()
        chat_history = [{"role": msg.role, "content": msg.content} for msg in history if msg.content and msg.content.strip()]

        if not request.image_base64 and is_ambiguous_first_message(request.query, chat_history):
            cleaned_query = (request.query or "").strip()
            response = AMBIGUOUS_FIRST_MESSAGE_FALLBACK.format(message=cleaned_query)
            db.add(ChatMessage(session_id=request.session_id, role="user", content=request.query))
            db.add(ChatMessage(session_id=request.session_id, role="assistant", content=response))
            db.commit()
            return ChatResponse(response=response, session_id=request.session_id, timestamp=json_timestamp(datetime.utcnow()))

        image_base64 = request.image_base64
        image_type = request.image_type or "image/jpeg"
        if image_base64:
            image_base64, image_type = validate_image_base64(image_base64, image_type)

        if budget_exhausted():
            return ChatResponse(response=BUDGET_EXCEEDED_FALLBACK, session_id=request.session_id, timestamp=json_timestamp(datetime.utcnow()))

        kb_content = load_knowledge_base()

        response = await call_claude(request.session_id, request.query, chat_history, kb_content, image_base64=image_base64, image_type=image_type)

        if request.query != "__greeting__":
            db.add(ChatMessage(session_id=request.session_id, role="user", content=request.query or "[Bild gesendet]"))
            assistant_message = ChatMessage(session_id=request.session_id, role="assistant", content=response)
            db.add(assistant_message)
            db.commit()

        return ChatResponse(response=response, session_id=request.session_id, timestamp=json_timestamp(datetime.utcnow()))
    except HTTPException:
        raise
    except Exception:
        logger.error("Chat error", exc_info=True)
        raise HTTPException(status_code=500)
    finally:
        db.close()


_INTERNAL_DOCS_DIR = _static_dir / "docs" / "internal"


@app.get("/internal")
@app.get("/internal/{path:path}")
async def internal_docs(request: Request, path: str = "", key: Optional[str] = None):
    """Interne Dashboards (docs/internal), nur mit Admin-Auth.

    Normalfall Team: Cloudflare Access schützt /internal/* (Policy "Team Wiso
    emails") → erster Seitenaufruf kommt mit gültigem Cf-Access-JWT an, wir
    setzen automatisch das Admin-Cookie (Auto-Mint) — damit funktionieren auch
    die fetch()-Calls der Dashboards auf /api/analytics|logs|reports|usage,
    die außerhalb der Access-Application liegen. Kein manueller Schritt nötig.

    Fallback ohne Cloudflare (lokal/Tests): einmalig /internal/?key=<ADMIN_API_KEY>
    aufrufen — prüft den Key, setzt dasselbe Cookie, redirectet.

    Das Cookie ist ein signiertes 8-h-Session-Token (JWT_SECRET), nicht der
    rohe Admin-Key.

    WICHTIG: Diese Route muss vor dem root-StaticFiles-Mount registriert sein
    (ist sie — der Mount kommt am Dateiende) und shadowed damit die alten
    /internal/*-URLs des Mounts. docs/public bleibt bewusst offen.
    """
    if key is not None:
        if not ADMIN_API_KEY or not hmac_lib.compare_digest(key.encode(), ADMIN_API_KEY.encode()):
            raise HTTPException(status_code=401, detail="Invalid admin key")
        response = RedirectResponse(url=request.url.path or "/internal/", status_code=302)
        _set_admin_cookie(response)
        return response

    auth_method = _admin_auth_method(request)
    if auth_method is None:
        _raise_admin_unauthorized()

    if not _INTERNAL_DOCS_DIR.is_dir():
        raise HTTPException(status_code=404, detail="Not found")

    # Pfad-Traversal-Schutz — gleiches Muster wie wiki_file_endpoint
    try:
        target = (_INTERNAL_DOCS_DIR / (path or "index.html")).resolve()
        target.relative_to(_INTERNAL_DOCS_DIR.resolve())
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="Invalid path")

    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    response = FileResponse(str(target))
    # Cookie-Auto-Mint (Nachtrag 2): Die Cloudflare-Access-Application ist auf
    # /internal/* begrenzt — die /api/*-Fetches der Dashboards bekommen deshalb
    # NIE den Cf-Access-JWT-Header. Beim ersten CF-verifizierten Seitenaufruf
    # setzen wir daher das Admin-Cookie, das die folgenden /api/*-Calls trägt.
    if auth_method == "cf" and not _admin_cookie_valid(request.cookies.get(ADMIN_COOKIE_NAME) or ""):
        _set_admin_cookie(response)
    return response


@app.get("/api/wiki")
async def wiki_endpoint():
    try:
        content = load_knowledge_base()
        return {"content": content, "format": "markdown", "timestamp": json_timestamp(datetime.utcnow())}
    except Exception:
        logger.error("Wiki endpoint error", exc_info=True)
        raise HTTPException(status_code=500)


@app.get("/api/wiki/file")
async def wiki_file_endpoint(path: str):
    """Return the raw content of a single knowledge_base file by relative path."""
    kb_dirs = [
        Path(__file__).parent.parent / "knowledge_base",
        Path("/knowledge_base"),
        Path("/app/knowledge_base"),
    ]
    kb_dir = next((d for d in kb_dirs if d.is_dir()), None)
    if not kb_dir:
        raise HTTPException(status_code=503, detail="Knowledge base not found")

    # Prevent directory traversal
    try:
        target = (kb_dir / path).resolve()
        target.relative_to(kb_dir.resolve())
    except (ValueError, Exception):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if target.suffix not in {".md", ".json"}:
        raise HTTPException(status_code=400, detail="Only .md and .json files allowed")

    content = target.read_text(encoding="utf-8")
    return {"path": path, "content": content, "format": target.suffix.lstrip(".")}


DEFAULT_ANALYTICS_DIR = Path(__file__).parent / "analytics"


def analytics_dirs() -> list[Path]:
    """Daily analytics exports live in backend/analytics; an env override may add another source."""
    dirs: list[Path] = [DEFAULT_ANALYTICS_DIR]
    configured = os.getenv("WIESEL_ANALYTICS_DIR")
    if configured:
        configured_dir = Path(configured)
        if configured_dir not in dirs:
            dirs.append(configured_dir)
    return dirs


def analytics_export_files(prefix: str = "analytics_") -> list[str]:
    return sorted({
        path.name
        for analytics_dir in analytics_dirs()
        for path in analytics_dir.glob(f"{prefix}*.json")
        if path.is_file() and path.name != "analytics_latest.json"
    })


@app.get("/api/analytics/files", dependencies=[Depends(require_admin)])
async def analytics_files():
    return {"files": analytics_export_files()}


@app.get("/api/analytics/month-files", dependencies=[Depends(require_admin)])
async def analytics_month_files(month: Optional[str] = None):
    if month is None:
        month = datetime.now().strftime("%Y-%m")
    elif not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(status_code=400, detail="Invalid month format; expected YYYY-MM")

    prefix = f"analytics_{month}-"
    files = analytics_export_files(prefix)
    return {"month": month, "files": files}


@app.get("/api/analytics/file/{filename}", dependencies=[Depends(require_admin)])
async def analytics_file(filename: str):
    if not re.fullmatch(r"analytics_\d{4}-\d{2}-\d{2}\.json", filename):
        raise HTTPException(status_code=400, detail="Invalid analytics filename")

    path = next((analytics_dir / filename for analytics_dir in analytics_dirs() if (analytics_dir / filename).is_file()), None)
    if path is None:
        raise HTTPException(status_code=404, detail="Analytics file not found")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.error("Invalid analytics JSON file: %s", path, exc_info=True)
        raise HTTPException(status_code=500, detail="Invalid analytics JSON")


@app.get("/api/reports/range", dependencies=[Depends(require_admin)])
async def reports_range(start: str, end: str):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start):
        raise HTTPException(status_code=400, detail="Invalid start format; expected YYYY-MM-DD")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
        raise HTTPException(status_code=400, detail="Invalid end format; expected YYYY-MM-DD")

    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end must be on or after start")

    range_start = app_time_to_utc_naive(datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=APP_TIMEZONE))
    range_end = app_time_to_utc_naive(datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, 999999, tzinfo=APP_TIMEZONE))

    db = SessionLocal()
    try:
        flags = db.query(ChatFlag).filter(
            ChatFlag.created_at >= range_start,
            ChatFlag.created_at <= range_end,
            ChatFlag.message_id.is_(None),
        ).order_by(ChatFlag.created_at).all()

        session_ids = sorted({flag.session_id for flag in flags})
        if not session_ids:
            return {"start": start_date.isoformat(), "end": end_date.isoformat(), "total_flags": 0, "total_sessions": 0, "sessions": []}

        messages = db.query(ChatMessage).filter(
            ChatMessage.session_id.in_(session_ids)
        ).order_by(ChatMessage.created_at).all()
        records = db.query(SessionRecord).filter(SessionRecord.id.in_(session_ids)).all()
        records_by_id = {record.id: record for record in records}

        flags_by_session: dict[str, list[dict]] = {}
        for flag in flags:
            flags_by_session.setdefault(flag.session_id, []).append({
                "id": flag.id,
                "tag": flag.tag,
                "created_at": json_timestamp(flag.created_at),
                "date": utc_naive_to_app_time(flag.created_at).date().isoformat(),
            })

        messages_by_session: dict[str, list[dict]] = {session_id: [] for session_id in session_ids}
        for message in messages:
            messages_by_session.setdefault(message.session_id, []).append({
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "created_at": json_timestamp(message.created_at),
            })

        sessions = []
        for session_id in session_ids:
            session_flags = flags_by_session.get(session_id, [])
            first_flag = session_flags[0] if session_flags else {}
            record = records_by_id.get(session_id)
            session_messages = messages_by_session.get(session_id, [])
            sessions.append({
                "session_id": session_id,
                "date": first_flag.get("date"),
                "flags": session_flags,
                "messages": session_messages,
                "message_count": len(session_messages),
                "session": {
                    "user_id": record.user_id if record else None,
                    "course_id": record.course_id if record else None,
                    "course_name": record.course_name if record else None,
                    "created_at": json_timestamp(record.created_at) if record else None,
                },
            })

        sessions.sort(key=lambda item: (item.get("date") or "", item["flags"][0]["created_at"] if item.get("flags") else ""))
        return {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "total_flags": len(flags),
            "total_sessions": len(sessions),
            "sessions": sessions,
        }
    finally:
        db.close()


@app.get("/api/usage/timeseries", dependencies=[Depends(require_admin)])
async def usage_timeseries(start: str, end: str, granularity: str = "hour", since: Optional[str] = None):
    if granularity != "hour":
        raise HTTPException(status_code=400, detail="Invalid granularity; only hour is supported")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start):
        raise HTTPException(status_code=400, detail="Invalid start format; expected YYYY-MM-DD")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
        raise HTTPException(status_code=400, detail="Invalid end format; expected YYYY-MM-DD")

    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end must be on or after start")

    range_start = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=APP_TIMEZONE)
    range_end = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, 999999, tzinfo=APP_TIMEZONE)
    now_app = datetime.now(APP_TIMEZONE)
    if end_date >= now_app.date():
        range_end = min(range_end, now_app)

    effective_start = range_start
    if since:
        try:
            parsed_since = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid since format; expected ISO local datetime")
        if parsed_since.tzinfo is None:
            parsed_since = parsed_since.replace(tzinfo=APP_TIMEZONE)
        else:
            parsed_since = parsed_since.astimezone(APP_TIMEZONE)
        if parsed_since > range_end:
            raise HTTPException(status_code=400, detail="since must be before end")
        effective_start = max(range_start, parsed_since)

    effective_start_utc = app_time_to_utc_naive(effective_start)
    range_end_utc = app_time_to_utc_naive(range_end)

    buckets: dict[datetime, int] = {}
    cursor = effective_start.replace(minute=0, second=0, microsecond=0)
    while cursor <= range_end:
        buckets[cursor] = 0
        cursor += timedelta(hours=1)

    db = SessionLocal()
    try:
        bucket_stats = {
            bucket: {
                "count": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "active_sessions": set(),
                "session_starts": 0,
            }
            for bucket in buckets
        }

        messages = db.query(ChatMessage.created_at, ChatMessage.role, ChatMessage.session_id).filter(
            ChatMessage.created_at >= effective_start_utc,
            ChatMessage.created_at <= range_end_utc,
        ).order_by(ChatMessage.created_at.asc()).all()
        for created_at, role, session_id in messages:
            if not created_at:
                continue
            created_at_app = utc_naive_to_app_time(created_at)
            bucket = created_at_app.replace(minute=0, second=0, microsecond=0)
            stat = bucket_stats.setdefault(bucket, {
                "count": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "active_sessions": set(),
                "session_starts": 0,
            })
            stat["count"] += 1
            if role == "user":
                stat["user_messages"] += 1
            elif role == "assistant":
                stat["assistant_messages"] += 1
            if session_id:
                stat["active_sessions"].add(session_id)

        session_rows = db.query(SessionRecord.created_at).filter(
            SessionRecord.created_at >= effective_start_utc,
            SessionRecord.created_at <= range_end_utc,
        ).all()
        for (created_at,) in session_rows:
            if not created_at:
                continue
            created_at_app = utc_naive_to_app_time(created_at)
            bucket = created_at_app.replace(minute=0, second=0, microsecond=0)
            stat = bucket_stats.setdefault(bucket, {
                "count": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "active_sessions": set(),
                "session_starts": 0,
            })
            stat["session_starts"] += 1

        points = []
        for bucket, stat in sorted(bucket_stats.items()):
            points.append({
                "timestamp": bucket.isoformat(),
                "count": stat["count"],
                "user_messages": stat["user_messages"],
                "assistant_messages": stat["assistant_messages"],
                "active_sessions": len(stat["active_sessions"]),
                "session_starts": stat["session_starts"],
            })

        total_messages = sum(point["count"] for point in points)
        total_user_messages = sum(point["user_messages"] for point in points)
        total_assistant_messages = sum(point["assistant_messages"] for point in points)
        total_session_starts = sum(point["session_starts"] for point in points)
        active_session_ids = {session_id for _, _, session_id in messages if session_id}
        user_message_times = [created_at for created_at, role, _ in messages if created_at and role == "user"]
        gaps = [
            (user_message_times[i] - user_message_times[i - 1]).total_seconds()
            for i in range(1, len(user_message_times))
            if 0 < (user_message_times[i] - user_message_times[i - 1]).total_seconds() < 6 * 3600
        ]
        peak = max(points, key=lambda point: point["user_messages"], default=None)
        days_count = max(1, (range_end - effective_start).total_seconds() / 86400)
        return {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "timezone": str(APP_TIMEZONE),
            "granularity": granularity,
            "total_messages": total_messages,
            "total_user_messages": total_user_messages,
            "total_assistant_messages": total_assistant_messages,
            "total_sessions": len(active_session_ids),
            "new_sessions": total_session_starts,
            "avg_messages_per_session": round(total_messages / len(active_session_ids), 2) if active_session_ids else 0,
            "avg_user_messages_per_session": round(total_user_messages / len(active_session_ids), 2) if active_session_ids else 0,
            "avg_messages_per_day": round(total_user_messages / days_count, 2),
            "avg_gap_seconds": round(sum(gaps) / len(gaps), 2) if gaps else None,
            "peak_hour": peak["timestamp"] if peak and peak["user_messages"] else None,
            "peak_hour_messages": peak["user_messages"] if peak else 0,
            "points": points,
        }
    finally:
        db.close()


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
            return {"ok": True, "flag_id": existing.id, "session_id": request.session_id, "tag": existing.tag, "created_at": json_timestamp(existing.created_at), "already_flagged": True}

        flag = ChatFlag(session_id=request.session_id, message_id=None, tag=tag)
        db.add(flag)
        db.commit()
        db.refresh(flag)
        return {"ok": True, "flag_id": flag.id, "session_id": request.session_id, "tag": tag, "created_at": json_timestamp(flag.created_at), "already_flagged": False}
    finally:
        db.close()


@app.get("/api/session/{session_id}", dependencies=[Depends(require_admin)])
async def session_endpoint(session_id: str):
    db = SessionLocal()
    try:
        session = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session_id": session.id, "user_id": session.user_id, "user_name": session.user_name, "course_id": session.course_id, "course_name": session.course_name, "user_role": session.user_role, "created_at": json_timestamp(session.created_at), "last_accessed": json_timestamp(session.last_accessed)}
    finally:
        db.close()


@app.get("/health")
async def health_check():
    llm_ok = bool(LLM_HEALTH["ok"])
    return {
        "status": "healthy" if llm_ok else "unhealthy",
        "timestamp": json_timestamp(datetime.utcnow()),
        "db": "connected",
        "llm": "connected" if llm_ok else "error",
        "last_llm_success": LLM_HEALTH["last_success"],
        "last_llm_error": LLM_HEALTH["last_error"],
    }


@app.post("/api/dev/session")
async def create_dev_session(request: Request):
    # Destruktiver Eval-Helfer (löscht Messages/Flags einer Session).
    # In production nicht verfügbar — Route existiert dort faktisch nicht.
    if ENVIRONMENT == "production":
        raise HTTPException(status_code=404, detail="Not found")
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


@app.get("/api/logs/daily", dependencies=[Depends(require_admin)])
async def get_daily_logs(date: Optional[str] = None):
    db = SessionLocal()
    try:
        target = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now(APP_TIMEZONE).date()
        day_start = app_time_to_utc_naive(datetime(target.year, target.month, target.day, 0, 0, 0, tzinfo=APP_TIMEZONE))
        day_end = app_time_to_utc_naive(datetime(target.year, target.month, target.day, 23, 59, 59, 999999, tzinfo=APP_TIMEZONE))
        messages = db.query(ChatMessage).filter(ChatMessage.created_at >= day_start, ChatMessage.created_at <= day_end).order_by(ChatMessage.created_at).all()
        flags = db.query(ChatFlag).filter(
            ChatFlag.created_at >= day_start,
            ChatFlag.created_at <= day_end,
            ChatFlag.message_id.is_(None),
        ).order_by(ChatFlag.created_at).all()
        flags_by_session: dict[str, list[dict]] = {}
        for f in flags:
            payload = {"id": f.id, "tag": f.tag, "created_at": json_timestamp(f.created_at)}
            flags_by_session.setdefault(f.session_id, []).append(payload)
        sessions: dict = {}
        for m in messages:
            if m.session_id not in sessions:
                sessions[m.session_id] = {"flags": flags_by_session.get(m.session_id, []), "messages": []}
            sessions[m.session_id]["messages"].append({"id": m.id, "role": m.role, "content": m.content, "created_at": json_timestamp(m.created_at)})
        for session_id, session_flags in flags_by_session.items():
            sessions.setdefault(session_id, {"flags": session_flags, "messages": []})
        return {"date": target.isoformat(), "total_messages": len(messages), "total_flags": len(flags), "total_sessions": len(sessions), "sessions": sessions}
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    logger.info("Wiesel Backend starting...")
    logger.info(f"Environment: {ENVIRONMENT}")
    logger.info(f"LTI Consumer Key: {LTI_CONSUMER_KEY}")
    logger.info(f"Database: {DATABASE_URL}")
    # SQLite härten: WAL-Mode reduziert Korruptionsrisiko bei parallelen
    # Zugriffen; quick_check erkennt eine kaputte DB beim Start statt im Betrieb.
    if DATABASE_URL.startswith("sqlite"):
        try:
            from sqlalchemy import text as sa_text
            with engine.connect() as conn:
                conn.execute(sa_text("PRAGMA journal_mode=WAL"))
                result = conn.execute(sa_text("PRAGMA quick_check")).fetchone()
                if result and result[0] != "ok":
                    logger.critical(f"SQLite quick_check FAILED: {result[0]} — DB prüfen/wiederherstellen (backend/db_backup.py)!")
                else:
                    logger.info("SQLite quick_check: ok (WAL aktiv)")
        except Exception:
            logger.error("SQLite startup check failed", exc_info=True)


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Wiesel Backend shutting down...")


# Broad docs mount: keep this after every API/page route, or it will eat the app.
if (_static_dir / "docs").exists():
    app.mount("/", StaticFiles(directory=str(_static_dir / "docs"), html=True), name="docs")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True, log_level="info")