"""Read-only helpers for Hermes' daily Wisdom chat-review retrieval."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# FAU-Matrikelnummern are normally eight digits. Deliberately do not mask dates,
# years or arbitrary short numeric facts in the review text.
_MATRIKEL_RE = re.compile(r"\b\d{8}\b")


def clean_text(value: object, limit: int = 10_000) -> str:
    """Normalize externally returned chat text and remove direct identifiers."""
    text = " ".join(str(value or "").split())
    text = _EMAIL_RE.sub("[E-Mail entfernt]", text)
    text = _IP_RE.sub("[IP entfernt]", text)
    text = _MATRIKEL_RE.sub("[Matrikelnummer entfernt]", text)
    return text[:limit].rstrip()


def _last_message_dates(db_path: Path, session_ids: set[str]) -> dict[str, str | None]:
    if not session_ids or not db_path.exists():
        return {}
    placeholders = ", ".join("?" for _ in session_ids)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"""SELECT session_id, MAX(datetime(created_at)) AS last_message_at
                FROM chat_messages WHERE session_id IN ({placeholders})
                GROUP BY session_id""",
            tuple(session_ids),
        ).fetchall()
        return {str(session_id): str(last_message_at) if last_message_at else None for session_id, last_message_at in rows}
    finally:
        conn.close()


def load_evaluations(evaluations_dir: Path, db_path: Path, since: date) -> list[dict[str, Any]]:
    """Return valid review JSONL records from `since`, enriched with last message time."""
    records: list[dict[str, Any]] = []
    if not evaluations_dir.exists():
        return records
    for path in sorted(evaluations_dir.glob("*.jsonl")):
        try:
            file_date = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if file_date < since:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            rating = raw.get("bewertung") if isinstance(raw, dict) else None
            if raw.get("status") != "ok" or not isinstance(rating, dict):
                continue
            session_id = raw.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                continue
            records.append({
                "session_id": session_id,
                "reviewed_at": str(raw.get("reviewed_at") or ""),
                "kategorie": clean_text(rating.get("kategorie"), 80),
                "schwere": rating.get("schwere"),
                "thema": clean_text(rating.get("thema"), 120),
                "begruendung": clean_text(rating.get("begruendung"), 500),
                "kb_vorschlag": clean_text(rating.get("kb_vorschlag"), 500) if rating.get("kb_vorschlag") else None,
                "auszug": [clean_text(item, 300) for item in rating.get("auszug", []) if clean_text(item, 300)] if isinstance(rating.get("auszug"), list) else [],
            })
    last_dates = _last_message_dates(db_path, {record["session_id"] for record in records})
    for record in records:
        record["letzte_nachricht_am"] = last_dates.get(record["session_id"])
    return records


def load_session_messages(db_path: Path, session_id: str) -> list[dict[str, str]]:
    """Return one session's transcript in chronological order, with identifiers masked."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """SELECT role, content, created_at FROM chat_messages
               WHERE session_id = ? ORDER BY datetime(created_at) ASC, id ASC""",
            (session_id,),
        ).fetchall()
        return [
            {"rolle": clean_text(role, 32), "text": clean_text(content), "zeitstempel": str(created_at)}
            for role, content, created_at in rows
        ]
    finally:
        conn.close()
