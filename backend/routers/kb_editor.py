"""Wissensbasis-Editor für das Team (interner Bereich, nur mit Admin-Login).

- Dateien auflisten mit Ampel („prüfen bis“), lesen, speichern, neu, löschen
- Jede Änderung wird mit Person, Zeitpunkt und Kommentar versioniert;
  jede Version lässt sich wiederherstellen (auch gelöschte Dateien)
- Prüfungen beim Speichern, Link-Prüfung, Probe-Antwort mit Entwurf
- Standardfragen: vom Team gepflegte Fragen + Stichworte, die in der Antwort
  vorkommen müssen (ersetzt die früheren Inhalts-Tests)
"""

from __future__ import annotations

import asyncio
import difflib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from backend import kb_store
from backend.jobs import source_watch

router = APIRouter(prefix="/api/kb", tags=["wissensbasis"])

# Von main.py über init() gesetzt (vermeidet zirkuläre Imports).
_SessionLocal = None
_ts = None
_identity = None
_ask = None
_invalidate = None
KBVersion = None
KBStandardFrage = None

MAX_STANDARD_QUESTIONS = 40


def init(Base, SessionLocal, json_timestamp, engine, identity, ask, invalidate):
    global _SessionLocal, _ts, _identity, _ask, _invalidate, KBVersion, KBStandardFrage
    _SessionLocal, _ts, _identity, _ask, _invalidate = SessionLocal, json_timestamp, identity, ask, invalidate

    class _KBVersion(Base):
        __tablename__ = "kb_versions"
        id = Column(Integer, primary_key=True, autoincrement=True)
        path = Column(String, index=True, nullable=False)
        action = Column(String, nullable=False)  # ausgangsstand|neu|geaendert|geloescht|wiederhergestellt
        content = Column(Text, nullable=False, default="")
        author = Column(String, default="")
        comment = Column(Text, default="")
        created_at = Column(DateTime, default=datetime.utcnow, index=True)

    class _KBStandardFrage(Base):
        __tablename__ = "kb_standardfragen"
        id = Column(Integer, primary_key=True, autoincrement=True)
        frage = Column(Text, nullable=False)
        stichworte = Column(Text, default="")  # eine Angabe pro Zeile / Komma
        notiz = Column(Text, default="")
        erstellt_von = Column(String, default="")
        created_at = Column(DateTime, default=datetime.utcnow)
        letzter_lauf = Column(DateTime, nullable=True)
        letztes_ok = Column(Boolean, nullable=True)
        letzte_antwort = Column(Text, default="")
        fehlende = Column(Text, default="")

    KBVersion, KBStandardFrage = _KBVersion, _KBStandardFrage
    for model in (KBVersion, KBStandardFrage):
        model.__table__.create(bind=engine, checkfirst=True)


# ── Hilfen ───────────────────────────────────────────────────────────────────

def _base():
    base = kb_store.kb_dir()
    if not base:
        raise HTTPException(status_code=503, detail="Wissensbasis-Ordner nicht gefunden.")
    return base


def _target(path: str):
    base = _base()
    try:
        return base, kb_store.safe_path(base, path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e) or "Ungültiger Dateipfad.")


def _mtime(path) -> str:
    return str(path.stat().st_mtime_ns)


def _write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _record(db, relative: str, action: str, content: str, who: str, comment: str = ""):
    db.add(KBVersion(path=relative, action=action, content=content, author=who, comment=(comment or "").strip()[:500]))


def _ensure_baseline(db, relative: str, current: Optional[str], who: str):
    """Vor der ersten Änderung den bisherigen Stand sichern (Rückweg)."""
    if current is None:
        return
    if not db.query(KBVersion.id).filter(KBVersion.path == relative).first():
        _record(db, relative, "ausgangsstand", current, "vor dem Editor", "Stand vor der ersten Änderung im Editor")


def _version_dict(v, with_content=False) -> dict:
    out = {"id": v.id, "path": v.path, "action": v.action, "author": v.author or "", "comment": v.comment or "",
           "created_at": _ts(v.created_at), "chars": len(v.content or "")}
    if with_content:
        out["content"] = v.content or ""
    return out


def _who(request: Request) -> str:
    try:
        return _identity(request)
    except Exception:
        return "Team"


def _changed():
    if _invalidate:
        _invalidate()


class FileSave(BaseModel):
    path: str
    body: str
    verantwortlich: str = ""
    pruefen_bis: str = ""
    base_mtime: Optional[str] = None
    kommentar: str = ""
    trotz_hinweisen: bool = True


class FileNew(BaseModel):
    folder: str = ""
    title: str = Field(min_length=2, max_length=120)
    verantwortlich: str = ""
    pruefen_bis: str = ""


class CheckRequest(BaseModel):
    body: str
    path: str = ""
    verantwortlich: str = ""
    pruefen_bis: str = ""


class ProbeRequest(BaseModel):
    frage: str = Field(min_length=2, max_length=1000)
    path: Optional[str] = None
    body: Optional[str] = None
    verantwortlich: str = ""
    pruefen_bis: str = ""


class StandardFrageIn(BaseModel):
    frage: str = Field(min_length=2, max_length=1000)
    stichworte: str = ""
    notiz: str = ""


def _meta(verantwortlich: str, pruefen_bis: str) -> dict:
    return {"verantwortlich": (verantwortlich or "").strip(), "pruefen_bis": (pruefen_bis or "").strip()}


# ── Dateien ──────────────────────────────────────────────────────────────────

@router.get("/files")
async def list_files():
    base = _base()
    files = [kb_store.describe(base, p) for p in kb_store.md_files(base)]
    files += [kb_store.describe(base, base / r) for r in kb_store.BEHAVIOR_FILES if (base / r).is_file()]
    quellen = source_watch.load_state(base)
    for f in files:
        q = quellen.get(f["path"]) or {}
        f["quelle_geaendert_seit"] = q.get("geaendert_seit")
        f["quelle_fehler"] = q.get("fehler")
    summary = {}
    for f in files:
        summary[f["status"]] = summary.get(f["status"], 0) + 1
    summary["quelle_geaendert"] = sum(1 for f in files if f["quelle_geaendert_seit"])
    total_chars = sum(f["chars"] for f in files)
    return {"files": files, "folders": kb_store.folders(base), "summary": summary, "total_chars": total_chars}


@router.get("/file")
async def get_file(path: str):
    base, target = _target(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden.")
    text = target.read_text(encoding="utf-8", errors="replace")
    meta, body = kb_store.parse(text)
    relative = kb_store.rel(base, target)
    info = kb_store.describe(base, target)
    q = source_watch.load_state(base).get(relative) or {}
    return {
        **info,
        "body": body,
        "base_mtime": _mtime(target),
        "issues": [] if info["auto"] else kb_store.check(meta, body, relative=relative),
        "quelle_status": q,
    }


@router.post("/check")
async def check_content(req: CheckRequest):
    return {"issues": kb_store.check(_meta(req.verantwortlich, req.pruefen_bis), req.body, relative=req.path)}


@router.put("/file")
async def save_file(req: FileSave, request: Request):
    base, target = _target(req.path)
    relative = kb_store.rel(base, target)
    if kb_store.is_auto(relative):
        raise HTTPException(status_code=400, detail="Diese Datei wird jede Nacht automatisch erzeugt und kann nicht bearbeitet werden.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden – wurde sie inzwischen gelöscht?")
    if req.base_mtime and req.base_mtime != _mtime(target):
        raise HTTPException(status_code=409, detail="Jemand hat diese Datei geändert, während du sie bearbeitet hast. Bitte deinen Text kopieren, die Datei neu laden und die Änderung erneut einfügen.")
    meta = _meta(req.verantwortlich, req.pruefen_bis)
    old_text = target.read_text(encoding="utf-8", errors="replace")
    old_meta, _ = kb_store.parse(old_text)
    meta = {**{k: v for k, v in old_meta.items() if k not in kb_store.META_KEYS}, **meta}
    issues = kb_store.check(meta, req.body, relative=relative)
    errors = [i for i in issues if i["level"] == "fehler"]
    if errors:
        raise HTTPException(status_code=422, detail=" ".join(i["text"] for i in errors))
    new_text = kb_store.compose(meta, req.body)
    if new_text == old_text.replace("\r\n", "\n"):
        return {"saved": False, "message": "Keine Änderung.", "base_mtime": _mtime(target), "issues": issues}
    who = _who(request)
    db = _SessionLocal()
    try:
        _ensure_baseline(db, relative, old_text, who)
        _write(target, new_text)
        _record(db, relative, "geaendert", new_text, who, req.kommentar)
        db.commit()
    finally:
        db.close()
    _changed()
    return {"saved": True, "base_mtime": _mtime(target), "issues": issues, "file": kb_store.describe(base, target)}


@router.post("/new")
async def new_file(req: FileNew, request: Request):
    base = _base()
    folder = (req.folder or "").strip().strip("/")
    if folder not in kb_store.folders(base):
        raise HTTPException(status_code=400, detail="Unbekannter Ordner.")
    name = kb_store.slugify(req.title) + ".md"
    relative = f"{folder}/{name}" if folder else name
    base, target = _target(relative)
    if target.exists():
        raise HTTPException(status_code=409, detail=f"Es gibt schon eine Datei „{relative}“. Bitte anderen Titel wählen.")
    meta = _meta(req.verantwortlich, req.pruefen_bis)
    try:
        kb_store.parse_date(meta["pruefen_bis"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    body = f"# {req.title.strip()}\n\nQuelle: \n\nHier den Inhalt eintragen – kurz, sachlich, mit Ansprechpartnern und Links.\n"
    text = kb_store.compose(meta, body)
    who = _who(request)
    _write(target, text)
    db = _SessionLocal()
    try:
        _record(db, relative, "neu", text, who, "Datei angelegt")
        db.commit()
    finally:
        db.close()
    _changed()
    return {"path": relative}


@router.delete("/file")
async def delete_file(path: str, request: Request, kommentar: str = ""):
    base, target = _target(path)
    relative = kb_store.rel(base, target)
    if kb_store.is_auto(relative):
        raise HTTPException(status_code=400, detail="Automatisch erzeugte Dateien können nicht gelöscht werden.")
    if kb_store.is_behavior(relative):
        raise HTTPException(status_code=400, detail="System-Prompt und Zusatzregeln können nicht gelöscht werden – nur bearbeitet.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden.")
    old_text = target.read_text(encoding="utf-8", errors="replace")
    who = _who(request)
    db = _SessionLocal()
    try:
        _ensure_baseline(db, relative, old_text, who)
        _record(db, relative, "geloescht", old_text, who, kommentar or "Datei gelöscht")
        db.commit()
    finally:
        db.close()
    target.unlink()
    _changed()
    return {"deleted": relative}


# ── Historie ─────────────────────────────────────────────────────────────────

@router.get("/history")
async def history(path: Optional[str] = None, limit: int = 100):
    db = _SessionLocal()
    try:
        q = db.query(KBVersion)
        if path:
            q = q.filter(KBVersion.path == path)
        q = q.filter(KBVersion.action != "ausgangsstand") if not path else q
        rows = q.order_by(KBVersion.id.desc()).limit(max(1, min(limit, 500))).all()
        return {"versions": [_version_dict(v) for v in rows]}
    finally:
        db.close()


@router.get("/deleted")
async def deleted_files():
    base = _base()
    db = _SessionLocal()
    try:
        rows = db.query(KBVersion).filter(KBVersion.action == "geloescht").order_by(KBVersion.id.desc()).all()
        out, seen = [], set()
        for v in rows:
            if v.path in seen:
                continue
            seen.add(v.path)
            try:
                exists = kb_store.safe_path(base, v.path).exists()
            except ValueError:
                exists = True
            if not exists:
                meta, body = kb_store.parse(v.content)
                out.append({**_version_dict(v), "title": kb_store.title_of(body, v.path)})
        return {"deleted": out}
    finally:
        db.close()


@router.get("/version/{version_id}")
async def version_detail(version_id: int):
    db = _SessionLocal()
    try:
        v = db.get(KBVersion, version_id)
        if not v:
            raise HTTPException(status_code=404, detail="Version nicht gefunden.")
        prev = (db.query(KBVersion).filter(KBVersion.path == v.path, KBVersion.id < v.id)
                .order_by(KBVersion.id.desc()).first())
        before = (prev.content if prev else "").splitlines()
        after = ("" if v.action == "geloescht" else v.content or "").splitlines()
        diff = list(difflib.unified_diff(before, after, "vorher", "nachher", lineterm="", n=2))
        return {**_version_dict(v, with_content=True), "diff": diff[2:] if len(diff) > 2 else []}
    finally:
        db.close()


@router.post("/restore/{version_id}")
async def restore(version_id: int, request: Request):
    base = _base()
    db = _SessionLocal()
    try:
        v = db.get(KBVersion, version_id)
        if not v:
            raise HTTPException(status_code=404, detail="Version nicht gefunden.")
        try:
            target = kb_store.safe_path(base, v.path)
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungültiger Dateipfad.")
        who = _who(request)
        current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else None
        _ensure_baseline(db, v.path, current, who)
        _write(target, v.content or "")
        when = v.created_at.strftime("%d.%m.%Y %H:%M") if v.created_at else "?"
        restored_path = v.path
        _record(db, restored_path, "wiederhergestellt", v.content or "", who, f"Stand vom {when} wiederhergestellt")
        db.commit()
    finally:
        db.close()
    _changed()
    return {"restored": restored_path}


# ── Quellen, Links, Probe ────────────────────────────────────────────────────

@router.post("/quelle-geprueft")
async def source_reviewed(path: str, request: Request):
    base, target = _target(path)
    source_watch.mark_reviewed(base, kb_store.rel(base, target), _who(request))
    return {"ok": True}


def _check_link(url: str) -> dict:
    import requests

    headers = {"User-Agent": source_watch.USER_AGENT}
    try:
        r = requests.head(url, headers=headers, timeout=8, allow_redirects=True)
        if r.status_code in (403, 405, 501) or r.status_code >= 500:
            r = requests.get(url, headers=headers, timeout=10, allow_redirects=True, stream=True)
            r.close()
        ok = r.status_code < 400
        return {"url": url, "ok": ok, "status": r.status_code,
                "hinweis": "" if ok else ("Seite nicht gefunden" if r.status_code == 404 else f"Fehler {r.status_code}")}
    except Exception:
        # Verbindungsfehler heißt nicht „Link kaputt“: FAU-Seiten sind z. B. von der VM aus gesperrt.
        return {"url": url, "ok": None, "status": None, "hinweis": "vom Server aus nicht prüfbar"}


@router.post("/links")
async def check_links(req: CheckRequest):
    links = kb_store.urls(req.body)[:40]
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = await asyncio.gather(*(loop.run_in_executor(pool, _check_link, u) for u in links))
    return {"links": list(results)}


@router.post("/probe")
async def probe(req: ProbeRequest):
    overrides = None
    if req.path and req.body is not None:
        base, target = _target(req.path)
        overrides = {kb_store.rel(base, target): kb_store.compose(_meta(req.verantwortlich, req.pruefen_bis), req.body)}
    answer = await _ask(req.frage, overrides)
    return {"antwort": answer, "mit_entwurf": overrides is not None}


# ── Standardfragen ───────────────────────────────────────────────────────────

def _keywords(raw: str) -> list[str]:
    parts = [p.strip() for chunk in (raw or "").splitlines() for p in chunk.split(",")]
    return [p for p in parts if p]


def _sf_dict(f) -> dict:
    return {"id": f.id, "frage": f.frage, "stichworte": _keywords(f.stichworte), "notiz": f.notiz or "",
            "erstellt_von": f.erstellt_von or "", "letzter_lauf": _ts(f.letzter_lauf) if f.letzter_lauf else None,
            "letztes_ok": f.letztes_ok, "letzte_antwort": f.letzte_antwort or "", "fehlende": _keywords(f.fehlende)}


def evaluate_answer(answer: str, keywords: list[str]) -> list[str]:
    """Fehlende Stichworte (Groß/Klein egal; „a | b“ = eins von beiden reicht)."""
    low = (answer or "").lower()
    missing = []
    for kw in keywords:
        options = [o.strip().lower() for o in kw.split("|") if o.strip()]
        if options and not any(o in low for o in options):
            missing.append(kw)
    return missing


@router.get("/standardfragen")
async def list_standard():
    db = _SessionLocal()
    try:
        return {"fragen": [_sf_dict(f) for f in db.query(KBStandardFrage).order_by(KBStandardFrage.id).all()]}
    finally:
        db.close()


@router.post("/standardfragen")
async def add_standard(req: StandardFrageIn, request: Request):
    db = _SessionLocal()
    try:
        if db.query(KBStandardFrage).count() >= MAX_STANDARD_QUESTIONS:
            raise HTTPException(status_code=400, detail=f"Maximal {MAX_STANDARD_QUESTIONS} Standardfragen.")
        f = KBStandardFrage(frage=req.frage.strip(), stichworte="\n".join(_keywords(req.stichworte)),
                            notiz=req.notiz.strip(), erstellt_von=_who(request))
        db.add(f)
        db.commit()
        db.refresh(f)
        return _sf_dict(f)
    finally:
        db.close()


@router.put("/standardfragen/{fid}")
async def update_standard(fid: int, req: StandardFrageIn):
    db = _SessionLocal()
    try:
        f = db.get(KBStandardFrage, fid)
        if not f:
            raise HTTPException(status_code=404, detail="Frage nicht gefunden.")
        f.frage, f.stichworte, f.notiz = req.frage.strip(), "\n".join(_keywords(req.stichworte)), req.notiz.strip()
        f.letztes_ok = None
        db.commit()
        return _sf_dict(f)
    finally:
        db.close()


@router.delete("/standardfragen/{fid}")
async def delete_standard(fid: int):
    db = _SessionLocal()
    try:
        f = db.get(KBStandardFrage, fid)
        if f:
            db.delete(f)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/standardfragen/run")
async def run_standard(fid: Optional[int] = None):
    db = _SessionLocal()
    try:
        q = db.query(KBStandardFrage)
        rows = [db.get(KBStandardFrage, fid)] if fid else q.order_by(KBStandardFrage.id).all()
        rows = [r for r in rows if r]
        for f in rows:
            answer = await _ask(f.frage, None)
            missing = evaluate_answer(answer, _keywords(f.stichworte))
            f.letzte_antwort, f.fehlende = answer, "\n".join(missing)
            f.letztes_ok, f.letzter_lauf = not missing, datetime.utcnow()
            db.commit()
        return {"fragen": [_sf_dict(f) for f in rows]}
    finally:
        db.close()
