"""
Agenda / Kanban router.
Provides CRUD endpoints for internal team agenda items stored in SQLite.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, String, DateTime, Text, Integer, text
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/agenda", tags=["agenda"])

VALID_STATUSES   = {"neu", "aktiv", "erledigt"}
VALID_PRIORITIES = {"low", "normal", "high"}


# ── Schemas ────────────────────────────────────────────────────────────────────

class AgendaCreateRequest(BaseModel):
    title:    str
    notes:    str = ""
    status:   str = "neu"
    priority: str = "normal"
    deadline: str | None = None   # ISO date string: YYYY-MM-DD


class AgendaUpdateRequest(BaseModel):
    title:    str | None = None
    notes:    str | None = None
    status:   str | None = None
    priority: str | None = None
    deadline: str | None = None


# ── Shared state (injected via init()) ────────────────────────────────────────

_get_db         = None
_json_timestamp = None
_AgendaItem     = None


def _db_dep():
    """Proper generator dependency: FastAPI runs the finally/close of get_db.
    The previous `Depends(_db_dep)` pulled only the first yield
    and leaked one DB session per request."""
    yield from _get_db()


def init(Base, get_db, json_timestamp, engine):
    """Called by main.py to wire up shared DB objects without circular imports."""
    global _get_db, _json_timestamp, _AgendaItem

    _get_db         = get_db
    _json_timestamp = json_timestamp

    class AgendaItem(Base):
        __tablename__ = "agenda"
        id         = Column(Integer, primary_key=True, autoincrement=True)
        title      = Column(Text, nullable=False)
        notes      = Column(Text,   default="")
        status     = Column(String, default="neu",    index=True)
        priority   = Column(String, default="normal")
        deadline   = Column(String, nullable=True)    # YYYY-MM-DD or None
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    _AgendaItem = AgendaItem

    # Migrate existing DB: add deadline column if missing
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE agenda ADD COLUMN deadline TEXT"))
            conn.commit()
    except Exception:
        pass  # column already exists or table not yet created – create_all handles the latter

    return AgendaItem


def _to_dict(item) -> dict:
    return {
        "id":         item.id,
        "title":      item.title,
        "notes":      item.notes or "",
        "status":     item.status,
        "priority":   item.priority,
        "deadline":   item.deadline or "",
        "created_at": _json_timestamp(item.created_at),
        "updated_at": _json_timestamp(item.updated_at),
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("")
async def agenda_list(db: Session = Depends(_db_dep)):
    items = db.query(_AgendaItem).order_by(_AgendaItem.created_at.desc()).all()
    return {"items": [_to_dict(i) for i in items]}


@router.post("", status_code=201)
async def agenda_create(req: AgendaCreateRequest, db: Session = Depends(_db_dep)):
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="title required")
    if req.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {VALID_STATUSES}")
    if req.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of {VALID_PRIORITIES}")
    item = _AgendaItem(
        title=req.title.strip(),
        notes=req.notes.strip(),
        status=req.status,
        priority=req.priority,
        deadline=req.deadline or None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_dict(item)


@router.patch("/{item_id}")
async def agenda_update(item_id: int, req: AgendaUpdateRequest, db: Session = Depends(_db_dep)):
    item = db.query(_AgendaItem).filter(_AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if req.title is not None:
        if not req.title.strip():
            raise HTTPException(status_code=400, detail="title cannot be empty")
        item.title = req.title.strip()
    if req.notes    is not None: item.notes    = req.notes.strip()
    if req.deadline is not None: item.deadline = req.deadline or None
    if req.status is not None:
        if req.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {VALID_STATUSES}")
        item.status = req.status
    if req.priority is not None:
        if req.priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail=f"priority must be one of {VALID_PRIORITIES}")
        item.priority = req.priority
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _to_dict(item)


@router.delete("/{item_id}", status_code=204)
async def agenda_delete(item_id: int, db: Session = Depends(_db_dep)):
    item = db.query(_AgendaItem).filter(_AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
