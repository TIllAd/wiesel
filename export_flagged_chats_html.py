#!/usr/bin/env python3
"""
Exportiert geflaggte Wiesel-Chats als lesbaren HTML-Report.

Standard: liest direkt aus backend/wiesel.db und nimmt ausschließlich Sessions mit
Chat-/Session-Flag. Alte per-message Flags werden ignoriert.

Usage:
  cd C:/Users/tillt/wiesel
  python export_flagged_chats_html.py --open
  python export_flagged_chats_html.py --days 30 --open
  python export_flagged_chats_html.py --json C:/Users/tillt/hermes/analytics/analytics_2026-06-28.json --open
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).parent / "backend" / "wiesel.db"
DEFAULT_OUT_DIR = Path(__file__).parent / "reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Geflaggte Wiesel-Chats als HTML exportieren.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Pfad zur SQLite-DB, Default: backend/wiesel.db")
    parser.add_argument("--json", help="Optional: analytics_YYYY-MM-DD.json statt DB lesen")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output-Ordner, Default: reports/")
    parser.add_argument("--days", type=int, default=30, help="Nur Sessions seit N Tagen aus DB, Default: 30")
    parser.add_argument("--include-unflagged", action="store_true", help="Auch ungeflaggte Sessions aufnehmen. Normalerweise Unsinn, aber bitte.")
    parser.add_argument("--open", action="store_true", help="HTML nach Export öffnen")
    parser.add_argument(
        "--split-gaps-minutes",
        type=int,
        default=20,
        help="Nachrichten innerhalb einer Session in Blöcke splitten, wenn länger als N Minuten Pause war. Default: 20. Mit 0 deaktivieren.",
    )
    return parser.parse_args()


def open_file(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path.resolve())  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path.resolve())])
        else:
            subprocess.Popen(["xdg-open", str(path.resolve())])
    except Exception as exc:
        print(f"Konnte HTML nicht automatisch öffnen: {exc}")


def qmark(value: Any) -> str:
    if value is None or value == "":
        return "–"
    return str(value)


def has_table(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def load_from_db(db_path: Path, days: int, include_unflagged: bool) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB nicht gefunden: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not has_table(conn, "sessions") or not has_table(conn, "chat_messages"):
            raise RuntimeError("DB enthält nicht die erwarteten Tabellen sessions/chat_messages")

        flags_exist = has_table(conn, "chat_flags")
        since = (datetime.now() - timedelta(days=days)).isoformat()

        sessions = conn.execute(
            """
            SELECT * FROM sessions
            WHERE created_at IS NULL OR created_at >= ?
            ORDER BY created_at DESC
            """,
            (since,),
        ).fetchall()

        exported_sessions: list[dict[str, Any]] = []
        for s in sessions:
            sid = s["id"]
            flag_rows = []
            if flags_exist:
                flag_rows = conn.execute(
                    """
                    SELECT id, session_id, tag, created_at
                    FROM chat_flags
                    WHERE session_id = ? AND message_id IS NULL
                    ORDER BY created_at ASC
                    """,
                    (sid,),
                ).fetchall()

            if not include_unflagged and not flag_rows:
                continue

            messages = conn.execute(
                """
                SELECT id, role, content, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (sid,),
            ).fetchall()

            session_flags = [
                {"id": f["id"], "tag": f["tag"], "created_at": f["created_at"]}
                for f in flag_rows
            ]

            exported_sessions.append(
                {
                    "session_id": sid,
                    "user": s["user_name"] if "user_name" in s.keys() else None,
                    "course": s["course_name"] if "course_name" in s.keys() else None,
                    "created_at": s["created_at"] if "created_at" in s.keys() else None,
                    "last_accessed": s["last_accessed"] if "last_accessed" in s.keys() else None,
                    "flags": session_flags,
                    "messages": [
                        {
                            "id": m["id"],
                            "role": m["role"],
                            "content": m["content"],
                            "created_at": m["created_at"],
                        }
                        for m in messages
                    ],
                }
            )

        return {
            "source": str(db_path),
            "mode": "sqlite",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "days": days,
            "sessions": exported_sessions,
        }
    finally:
        conn.close()


def load_from_analytics_json(json_path: Path, include_unflagged: bool) -> dict[str, Any]:
    if not json_path.exists():
        raise FileNotFoundError(f"JSON nicht gefunden: {json_path}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    exported_sessions: list[dict[str, Any]] = []

    for s in data.get("sessions", []):
        session_flags = s.get("flags", []) or []
        messages = []
        for idx, turn in enumerate(s.get("verlauf", []), start=1):
            user_time = turn.get("zeitpunkt")
            messages.append(
                {
                    "id": f"{idx}u",
                    "role": "user",
                    "content": turn.get("frage", ""),
                    "created_at": user_time,
                }
            )
            messages.append(
                {
                    "id": f"{idx}a",
                    "role": "assistant",
                    "content": turn.get("antwort", ""),
                    "created_at": user_time,
                }
            )

        if not include_unflagged and not session_flags:
            continue

        exported_sessions.append(
            {
                "session_id": s.get("session_id"),
                "user": s.get("user"),
                "course": s.get("kurs"),
                "created_at": s.get("gestartet_am"),
                "last_accessed": None,
                "flags": session_flags,
                "messages": messages,
            }
        )

    return {
        "source": str(json_path),
        "mode": "analytics-json",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "period": data.get("periode"),
        "sessions": exported_sessions,
    }


def short(text: str, n: int = 180) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= n else cleaned[: n - 1] + "…"


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def split_message_blocks(messages: list[dict[str, Any]], gap_minutes: int) -> list[dict[str, Any]]:
    """Gruppiert lange Debug-Sessions in lesbare Gesprächsblöcke.

    Debug Mode nutzt oft dieselbe session_id immer wieder. Ein Session-Flag ist dann korrekt,
    aber der Export wirkt wie ein Chat-Monster. Also splitten wir rein visuell nach Zeitlücken.
    Die DB bleibt unverändert. Kleine Gnade für menschliche Augen.
    """
    if not messages:
        return []
    if gap_minutes <= 0:
        return [{"start": messages[0].get("created_at"), "end": messages[-1].get("created_at"), "messages": messages}]

    blocks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    previous_dt: datetime | None = None
    gap = timedelta(minutes=gap_minutes)

    for message in messages:
        current_dt = parse_dt(message.get("created_at"))
        if current and current_dt and previous_dt and current_dt - previous_dt > gap:
            blocks.append({"start": current[0].get("created_at"), "end": current[-1].get("created_at"), "messages": current})
            current = []
        current.append(message)
        if current_dt:
            previous_dt = current_dt

    if current:
        blocks.append({"start": current[0].get("created_at"), "end": current[-1].get("created_at"), "messages": current})
    return blocks


def render_html(report: dict[str, Any], split_gaps_minutes: int = 20) -> str:
    sessions = report.get("sessions", [])
    total_messages = sum(len(s.get("messages", [])) for s in sessions)
    total_session_flags = sum(len(s.get("flags", [])) for s in sessions)


    overview_rows = []
    cards = []
    for idx, s in enumerate(sessions, start=1):
        sid = qmark(s.get("session_id"))
        anchor = f"s{idx}"
        session_flags = s.get("flags", []) or []
        messages = s.get("messages", []) or []
        first_user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
        flag_badges = "".join(
            f"<span class='flag'>{html.escape(qmark(f.get('tag')))} · {html.escape(qmark(f.get('created_at')))}</span>"
            for f in session_flags
        ) or "<span class='muted'>keine Session-Flags</span>"

        overview_rows.append(
            "<tr>"
            f"<td><a href='#{anchor}'>{idx}</a></td>"
            f"<td>{html.escape(qmark(s.get('created_at')))}</td>"
            f"<td>{html.escape(qmark(s.get('user')))}</td>"
            f"<td>{html.escape(qmark(s.get('course')))}</td>"
            f"<td>{len(session_flags)}</td>"
            f"<td>{html.escape(short(first_user))}</td>"
            "</tr>"
        )

        block_html = []
        blocks = split_message_blocks(messages, split_gaps_minutes)
        for block_idx, block in enumerate(blocks, start=1):
            block_messages = block.get("messages", []) or []
            first_user_in_block = next((m.get("content", "") for m in block_messages if m.get("role") == "user"), "")
            message_html = []
            for m in block_messages:
                role = qmark(m.get("role"))
                role_class = "user" if role == "user" else "assistant" if role == "assistant" else "other"
                message_html.append(
                    f"<div class='message {role_class}'>"
                    f"<div class='message-meta'>{html.escape(role)} · ID {html.escape(qmark(m.get('id')))} · {html.escape(qmark(m.get('created_at')))}</div>"
                    f"<pre>{html.escape(qmark(m.get('content')))}</pre>"
                    "</div>"
                )
            open_attr = " open" if block_idx == len(blocks) else ""
            block_html.append(
                f"<details class='block'{open_attr}>"
                f"<summary><strong>Block {block_idx}</strong> · {len(block_messages)} Nachrichten · {html.escape(qmark(block.get('start')))} → {html.escape(qmark(block.get('end')))} · erster Prompt: {html.escape(short(first_user_in_block, 120))}</summary>"
                f"{''.join(message_html)}"
                "</details>"
            )

        debug_warning = ""
        if sid == "debug_session_wiesel" or len(messages) > 80:
            debug_warning = (
                "<div class='warning'><strong>Hinweis:</strong> Diese Session ist ungewöhnlich lang. "
                "Das kann bei alten Debug-Sessions passieren, die noch dieselbe session_id wiederverwendet haben, "
                "oder bei absichtlich langen Tests. Der Report splittet das hier nur visuell in Zeitblöcke. "
                "Die DB bleibt unverändert.</div>"
            )

        cards.append(
            f"<section class='card' id='{anchor}'>"
            f"<div class='card-head'><h2>#{idx} · {html.escape(sid)}</h2><a href='#top'>nach oben</a></div>"
            f"<div class='meta'>User: {html.escape(qmark(s.get('user')))} · Kurs: {html.escape(qmark(s.get('course')))} · Start: {html.escape(qmark(s.get('created_at')))} · Letzter Zugriff: {html.escape(qmark(s.get('last_accessed')))}</div>"
            f"<div class='flags'>{flag_badges}</div>"
            f"{debug_warning}"
            f"<details open><summary>{len(messages)} Nachrichten anzeigen · in {len(blocks)} Blöcke gesplittet</summary>{''.join(block_html)}</details>"
            "</section>"
        )

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Wiesel · Geflaggte Chats</title>
<style>
:root {{ color-scheme: dark; --bg:#0d1117; --card:#161b22; --line:#30363d; --text:#e6edf3; --muted:#8b949e; --yellow:#d29922; --blue:#58a6ff; --user:#102033; --assistant:#161b22; --flag:#e3b341; --warn:#ffcc66; }}
body {{ margin:0; padding:32px; background:var(--bg); color:var(--text); font:15px/1.5 system-ui, -apple-system, Segoe UI, sans-serif; }}
h1 {{ margin:0 0 8px; font-size:30px; }}
h2 {{ margin:0; font-size:18px; }}
a {{ color:var(--blue); }}
.meta, .muted, .message-meta {{ color:var(--muted); }}
.stats {{ display:flex; gap:12px; flex-wrap:wrap; margin:18px 0 24px; }}
.stat {{ padding:10px 14px; background:var(--card); border:1px solid var(--line); border-radius:12px; }}
.table-wrap {{ overflow:auto; margin:20px 0 28px; border:1px solid var(--line); border-radius:12px; }}
table {{ width:100%; border-collapse:collapse; background:var(--card); }}
th, td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ color:var(--muted); font-weight:600; }}
.card {{ margin:22px 0; padding:18px; background:var(--card); border:1px solid rgba(210,153,34,.55); border-radius:14px; }}
.card-head {{ display:flex; align-items:center; justify-content:space-between; gap:16px; }}
.flags {{ margin:12px 0; }}
.flag {{ display:inline-block; margin:4px 6px 0 0; padding:3px 8px; border-radius:999px; background:rgba(210,153,34,.18); color:var(--flag); font-size:12px; font-weight:600; }}
details {{ margin-top:12px; }}
summary {{ cursor:pointer; color:var(--muted); margin-bottom:12px; }}
.block {{ padding:10px 12px; border:1px solid var(--line); border-radius:12px; background:rgba(255,255,255,.02); }}
.block + .block {{ margin-top:12px; }}
.warning {{ margin:12px 0; padding:10px 12px; border:1px solid rgba(255,204,102,.55); background:rgba(255,204,102,.10); color:var(--warn); border-radius:12px; }}
.message {{ border:1px solid var(--line); border-radius:12px; margin:10px 0; overflow:hidden; }}
.message.user {{ background:var(--user); }}
.message.assistant {{ background:var(--assistant); }}
.message-meta {{ padding:8px 12px; border-bottom:1px solid var(--line); font-size:12px; }}
pre {{ margin:0; padding:12px; white-space:pre-wrap; word-wrap:break-word; font:14px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; }}
.empty {{ padding:24px; border:1px dashed var(--line); border-radius:14px; color:var(--muted); }}
</style>
</head>
<body id="top">
<h1>Wiesel · Geflaggte Chats</h1>
<div class="meta">Quelle: {html.escape(qmark(report.get('source')))} · Modus: {html.escape(qmark(report.get('mode')))} · Export: {html.escape(qmark(report.get('generated_at')))}</div>
<div class="stats">
  <div class="stat">Geflaggte Sessions: <strong>{len(sessions)}</strong></div>
  <div class="stat">Nachrichten: <strong>{total_messages}</strong></div>
  <div class="stat">Session-Flags: <strong>{total_session_flags}</strong></div>
</div>
<div class="table-wrap"><table><thead><tr><th>#</th><th>Start</th><th>User</th><th>Kurs</th><th>Session-Flags</th><th>Erster Prompt</th></tr></thead><tbody>{''.join(overview_rows)}</tbody></table></div>
{''.join(cards) if cards else '<div class="empty">Keine geflaggten Chats gefunden. Entweder hat niemand geklickt, oder ihr exportiert aus der falschen DB. Beides wäre typisch.</div>'}
</body>
</html>"""


def render_markdown(report: dict[str, Any], split_gaps_minutes: int = 20) -> str:
    lines = []
    lines.append(f"# Wiesel · Geflaggte Chats · {report.get('generated_at')}")
    lines.append("")
    lines.append(f"Quelle: {report.get('source')}")
    lines.append("")
    for idx, s in enumerate(report.get("sessions", []), start=1):
        lines.append(f"## {idx}. {s.get('session_id')}")
        lines.append(f"User: {qmark(s.get('user'))} · Kurs: {qmark(s.get('course'))} · Start: {qmark(s.get('created_at'))}")
        lines.append("")
        if s.get("flags"):
            lines.append("Session-Flags: " + ", ".join(f"{f.get('tag')} ({f.get('created_at')})" for f in s.get("flags", [])))
            lines.append("")
        messages = s.get("messages", []) or []
        if s.get("session_id") == "debug_session_wiesel" or len(messages) > 80:
            lines.append("> Hinweis: ungewöhnlich lange Session. Das kann bei alten Debug-Sessions passieren, die noch dieselbe session_id wiederverwendet haben, oder bei absichtlich langen Tests. Der Export splittet nur visuell nach Zeitlücken; die DB bleibt unverändert.")
            lines.append("")
        for block_idx, block in enumerate(split_message_blocks(messages, split_gaps_minutes), start=1):
            block_messages = block.get("messages", []) or []
            lines.append(f"### Block {block_idx} · {len(block_messages)} Nachrichten · {qmark(block.get('start'))} → {qmark(block.get('end'))}")
            lines.append("")
            for m in block_messages:
                lines.append(f"#### {m.get('role')} · {m.get('created_at')}")
                lines.append("")
                lines.append(qmark(m.get("content")))
                lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.json:
        report = load_from_analytics_json(Path(args.json), args.include_unflagged)
    else:
        report = load_from_db(Path(args.db), args.days, args.include_unflagged)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = out_dir / f"flagged-chats-{ts}.html"
    md_path = out_dir / f"flagged-chats-{ts}.md"
    html_path.write_text(render_html(report, args.split_gaps_minutes), encoding="utf-8")
    md_path.write_text(render_markdown(report, args.split_gaps_minutes), encoding="utf-8")

    print("Geflaggte Chats exportiert:")
    print(f"  Sessions: {len(report.get('sessions', []))}")
    print(f"  HTML: {html_path}")
    print(f"  Markdown: {md_path}")

    if args.open:
        open_file(html_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
