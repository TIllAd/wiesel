"""
Mentorenprogramm router.
Stores one sparse internal working document for the Wiesel team.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, Text
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/mentor", tags=["mentor"])


class MentorDocUpdateRequest(BaseModel):
    content: str = ""


_get_db = None
_json_timestamp = None
_MentorDoc = None


def _db_dep():
    """Proper generator dependency (see agenda.py) — no leaked sessions."""
    yield from _get_db()

OLD_DEFAULT_CONTENT = """# Mentorenprogramm\n\n## Ziele\n\n\n## Wer testet?\n\n\n## Offene Fragen\n\n\n## Nächste Schritte\n\n"""

DEFAULT_CONTENT = """**WiSo Wiesel**  
Mentoren-Feedback  
FAU WiSo · Unwritten Studio · Juni 2026

# Was ist Wiesel?

Wiesel ist ein KI-gestützter Studienbegleiter für Erstsemesterstudierende der WiSo-Fakultät. Er beantwortet Fragen rund um Studienstart, Prüfungen, Campus-Systeme und Orientierung — als Character mit Haltung, nicht als FAQ-Datenbank.

Er kennt das Uni-Labyrinth: Campo, StudOn, Mensa, ÖPNV, Prüfungsamt, BAföG — aber testet selbst, was er weiß und was nicht.

# Eure Aufgabe

Benutzt Wiesel einfach. Keine Checkliste, keine vorgeschriebenen Fragen.

Stellt Fragen, die euch als Ersti wirklich durch den Kopf gegangen sind — oder die ihr euch damals gewünscht hättet stellen zu können. Seid ehrlich, seid neugierig, versucht ihn auch mal aus der Reserve zu locken.

Danach: kurze Rückmeldung an uns. Wie ihr das macht, ist egal — Signal-Nachricht, kurze Mail, mündlich beim nächsten Treffen.

# Was uns interessiert

Ihr müsst kein Formular ausfüllen. Aber diese drei Fragen helfen beim Fokussieren:

**1. Was war falsch oder fehlend?**  
Falsche Fristen, falsche Links, falsche Infos — oder eine Frage, die Wiesel gar nicht beantworten konnte, obwohl er es sollte.

**2. Wie hat er sich angefühlt?**  
War der Ton okay? Hat er geklungen wie jemand, dem man vertraut? Oder eher wie ein Formular mit Augen? War es zu viel Character?

**3. Was hat euch überrascht — positiv oder negativ?**  
Irgendwas, was ihr nicht erwartet hättet. In beide Richtungen.

# Feedback schicken

Kein bestimmtes Format nötig. Was zählt:

– Was habt ihr gefragt?  
– Was hat Wiesel geantwortet?  
– Was war daran gut oder schlecht?

An: till.adelmann@fau.de

Auch eine einzige Beobachtung ist wertvoll.

# Wiesel ausprobieren

**Link:** https://wiesel.chatbot-wiso.de/chat

Funktioniert im Browser, kein Login nötig.

_Danke — euer Feedback macht Wiesel besser._
"""


def init(Base, get_db, json_timestamp, engine):
    """Called by main.py to wire up shared DB objects without circular imports."""
    global _get_db, _json_timestamp, _MentorDoc

    _get_db = get_db
    _json_timestamp = json_timestamp

    class MentorDoc(Base):
        __tablename__ = "mentor_docs"
        id = Column(Integer, primary_key=True)
        content = Column(Text, default=DEFAULT_CONTENT)
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    _MentorDoc = MentorDoc
    _MentorDoc.__table__.create(bind=engine, checkfirst=True)
    return MentorDoc


def _to_dict(doc) -> dict:
    return {
        "id": doc.id,
        "content": doc.content or "",
        "created_at": _json_timestamp(doc.created_at),
        "updated_at": _json_timestamp(doc.updated_at),
    }


def _get_or_create_doc(db: Session):
    doc = db.query(_MentorDoc).filter(_MentorDoc.id == 1).first()
    if doc:
        if doc.content == OLD_DEFAULT_CONTENT:
            doc.content = DEFAULT_CONTENT
            doc.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(doc)
        return doc
    doc = _MentorDoc(id=1, content=DEFAULT_CONTENT)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("")
async def mentor_doc_get(db: Session = Depends(_db_dep)):
    return _to_dict(_get_or_create_doc(db))


@router.put("")
async def mentor_doc_update(req: MentorDocUpdateRequest, db: Session = Depends(_db_dep)):
    doc = _get_or_create_doc(db)
    doc.content = req.content
    doc.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(doc)
    return _to_dict(doc)
