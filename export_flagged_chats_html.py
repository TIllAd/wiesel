#!/usr/bin/env python3
"""
Exportiert geflaggte Wiesel-Chats als lesbaren HTML-Report.
Sidebar-Layout: linke Sidebar mit Session-Liste, rechts Chat-Ansicht.

Usage:
  python export_flagged_chats_html.py --open
  python export_flagged_chats_html.py --days 30 --open
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).parent / "backend" / "wiesel.db"
DEFAULT_OUT_DIR = Path(__file__).parent / "reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--json", help="Optional: analytics JSON statt DB")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--include-unflagged", action="store_true")
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--split-gaps-minutes", type=int, default=20)
    return parser.parse_args()


def open_file(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path.resolve())
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path.resolve())])
        else:
            subprocess.Popen(["xdg-open", str(path.resolve())])
    except Exception as exc:
        print(f"Konnte HTML nicht öffnen: {exc}")


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
        flags_exist = has_table(conn, "chat_flags")
        since = (datetime.now() - timedelta(days=days)).isoformat()
        sessions = conn.execute(
            "SELECT * FROM sessions WHERE created_at IS NULL OR created_at >= ? ORDER BY created_at DESC",
            (since,),
        ).fetchall()

        exported = []
        for s in sessions:
            sid = s["id"]
            flag_rows = []
            if flags_exist:
                flag_rows = conn.execute(
                    "SELECT id, session_id, tag, created_at FROM chat_flags WHERE session_id = ? AND message_id IS NULL ORDER BY created_at ASC",
                    (sid,),
                ).fetchall()
            if not include_unflagged and not flag_rows:
                continue
            messages = conn.execute(
                "SELECT id, role, content, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC, id ASC",
                (sid,),
            ).fetchall()
            exported.append({
                "session_id": sid,
                "user": s["user_name"] if "user_name" in s.keys() else None,
                "course": s["course_name"] if "course_name" in s.keys() else None,
                "created_at": s["created_at"] if "created_at" in s.keys() else None,
                "flags": [{"id": f["id"], "tag": f["tag"], "created_at": f["created_at"]} for f in flag_rows],
                "messages": [{"id": m["id"], "role": m["role"], "content": m["content"], "created_at": m["created_at"]} for m in messages],
            })
        return {"source": str(db_path), "mode": "sqlite", "generated_at": datetime.now().isoformat(timespec="seconds"), "sessions": exported}
    finally:
        conn.close()


def short(text: str, n: int = 80) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= n else cleaned[:n-1] + "…"


def render_inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    def link_repl(m):
        return f"<a href='{html.escape(m.group(2), quote=True)}' target='_blank'>{m.group(1)}</a>"
    escaped = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", link_repl, escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    return escaped


def render_message_markdown(content: Any) -> str:
    lines = qmark(content).splitlines()
    out: list[str] = []
    paragraph: list[str] = []
    in_ul = in_ol = in_code = False
    code_lines: list[str] = []

    def flush_p():
        nonlocal paragraph
        if paragraph:
            out.append(f"<p>{'<br>'.join(render_inline_markdown(l) for l in paragraph)}</p>")
            paragraph = []

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul: out.append("</ul>"); in_ul = False
        if in_ol: out.append("</ol>"); in_ol = False

    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        if s.startswith("```"):
            flush_p(); close_lists()
            if in_code:
                out.append(f"<pre class='code-block'><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []; in_code = False
            else:
                in_code = True
            continue
        if in_code: code_lines.append(line); continue
        if not s: flush_p(); close_lists(); continue
        h = re.match(r"^(#{1,4})\s+(.+)$", s)
        if h:
            flush_p(); close_lists()
            lvl = min(len(h.group(1)) + 2, 6)
            out.append(f"<h{lvl}>{render_inline_markdown(h.group(2))}</h{lvl}>"); continue
        b = re.match(r"^[-*]\s+(.+)$", s)
        if b:
            flush_p()
            if in_ol: out.append("</ol>"); in_ol = False
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{render_inline_markdown(b.group(1))}</li>"); continue
        n = re.match(r"^\d+[.)]\s+(.+)$", s)
        if n:
            flush_p()
            if in_ul: out.append("</ul>"); in_ul = False
            if not in_ol: out.append("<ol>"); in_ol = True
            out.append(f"<li>{render_inline_markdown(n.group(1))}</li>"); continue
        q = re.match(r"^>\s?(.+)$", s)
        if q:
            flush_p(); close_lists()
            out.append(f"<blockquote>{render_inline_markdown(q.group(1))}</blockquote>"); continue
        close_lists(); paragraph.append(line)

    flush_p(); close_lists()
    if in_code:
        out.append(f"<pre class='code-block'><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "".join(out) or "<p>–</p>"


def render_html(report: dict[str, Any], split_gaps_minutes: int = 20) -> str:
    sessions = report.get("sessions", [])
    total_messages = sum(len(s.get("messages", [])) for s in sessions)
    total_flags = sum(len(s.get("flags", [])) for s in sessions)

    sidebar_items = []
    for idx, s in enumerate(sessions, start=1):
        flags = s.get("flags", [])
        messages = s.get("messages", [])
        first_user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
        time_str = (s.get("created_at") or "")[:16].replace("T", " ")
        flag_tag = flags[0].get("tag", "") if flags else ""
        sidebar_items.append(
            f"<div class='sidebar-item' onclick=\"showSession('s{idx}')\" id='nav-s{idx}'>"
            f"<div class='si-num'>#{idx}</div>"
            f"<div class='si-body'>"
            f"<div class='si-flag'>⚠️ {html.escape(flag_tag)}</div>"
            f"<div class='si-time'>{html.escape(time_str)} · {len(messages)} Msgs</div>"
            f"<div class='si-preview'>{html.escape(short(first_user, 60))}</div>"
            f"</div></div>"
        )

    panels = []
    for idx, s in enumerate(sessions, start=1):
        messages = s.get("messages", [])
        flags = s.get("flags", [])
        time_str = (s.get("created_at") or "")[:16].replace("T", " ")
        flag_badges = "".join(
            f"<span class='flag'>⚠️ {html.escape(f.get('tag',''))} · {html.escape((f.get('created_at') or '')[:16])}</span>"
            for f in flags
        )
        msg_html = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "") or ""
            ts = (m.get("created_at") or "")[:16].replace("T", " ")
            role_label = "🎓 Student" if role == "user" else "🐾 Wiesel"
            msg_html.append(
                f"<div class='msg msg-{role}'>"
                f"<div class='msg-header'><span class='msg-role'>{role_label}</span><span class='msg-time'>{html.escape(ts)}</span></div>"
                f"<div class='msg-body'>{render_message_markdown(content)}</div>"
                f"</div>"
            )
        display = "flex" if idx == 1 else "none"
        panels.append(
            f"<div class='panel' id='s{idx}' style='display:{display}'>"
            f"<div class='panel-header'>"
            f"<div><strong>Session #{idx}</strong> · {html.escape(time_str)} · {len(messages)} Nachrichten</div>"
            f"<div class='panel-flags'>{flag_badges}</div>"
            f"</div>"
            f"<div class='chat-area'>{''.join(msg_html)}</div>"
            f"</div>"
        )

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wiesel · Geflaggte Chats</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{ --bg:#0d1117; --sidebar:#161b22; --card:#1c2128; --line:#30363d; --text:#e6edf3; --muted:#8b949e; --blue:#58a6ff; --yellow:#d29922; --flag:#e3b341; --user-bg:#0d2137; --bot-bg:#1c2128; --user-border:#1f4a73; --bot-border:#30363d; }}
body {{ background:var(--bg); color:var(--text); font:15px/1.6 system-ui,-apple-system,sans-serif; height:100vh; display:flex; flex-direction:column; overflow:hidden; }}
.topbar {{ padding:14px 20px; background:var(--sidebar); border-bottom:1px solid var(--line); display:flex; align-items:center; gap:16px; flex-shrink:0; }}
.topbar h1 {{ font-size:18px; font-weight:700; }}
.pill {{ padding:4px 10px; background:rgba(88,166,255,.12); border:1px solid rgba(88,166,255,.3); border-radius:999px; font-size:13px; color:var(--blue); }}
.gen {{ color:var(--muted); font-size:12px; margin-left:auto; }}
.layout {{ display:flex; flex:1; overflow:hidden; }}
.sidebar {{ width:280px; flex-shrink:0; background:var(--sidebar); border-right:1px solid var(--line); overflow-y:auto; }}
.sidebar-item {{ padding:14px 16px; border-bottom:1px solid var(--line); cursor:pointer; display:flex; gap:10px; transition:background .15s; }}
.sidebar-item:hover {{ background:rgba(255,255,255,.04); }}
.sidebar-item.active {{ background:rgba(88,166,255,.1); border-left:3px solid var(--blue); padding-left:13px; }}
.si-num {{ color:var(--muted); font-size:13px; font-weight:600; width:22px; flex-shrink:0; padding-top:1px; }}
.si-body {{ flex:1; min-width:0; }}
.si-flag {{ font-size:13px; font-weight:600; color:var(--flag); }}
.si-time {{ font-size:12px; color:var(--muted); margin-top:2px; }}
.si-preview {{ font-size:13px; margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:var(--muted); }}
.main {{ flex:1; overflow:hidden; }}
.panel {{ flex-direction:column; height:100%; overflow:hidden; }}
.panel-header {{ padding:16px 24px; background:var(--card); border-bottom:1px solid var(--line); flex-shrink:0; }}
.panel-header strong {{ font-size:16px; }}
.panel-flags {{ margin-top:8px; }}
.flag {{ display:inline-block; padding:3px 10px; border-radius:999px; background:rgba(210,153,34,.18); color:var(--flag); font-size:12px; font-weight:600; margin-right:6px; }}
.chat-area {{ flex:1; overflow-y:auto; padding:24px 32px; display:flex; flex-direction:column; gap:20px; min-width:0; width:100%; }}
.msg {{ border-radius:14px; max-width:75%; min-width:0; box-sizing:border-box; }}
.msg-user {{ background:var(--user-bg); border:1px solid var(--user-border); align-self:flex-end; }}
.msg-assistant {{ background:var(--bot-bg); border:1px solid var(--bot-border); align-self:flex-start; }}
.msg-header {{ padding:8px 14px; display:flex; justify-content:space-between; align-items:center; gap:16px; border-bottom:1px solid var(--line); flex-wrap:wrap; }}
.msg-role {{ font-size:12px; font-weight:700; color:var(--muted); }}
.msg-time {{ font-size:11px; color:var(--muted); }}
.msg-body {{ padding:14px 18px; word-break:break-word; overflow-wrap:break-word; }}
.msg-body p {{ margin:0 0 10px; }}
.msg-body p:last-child {{ margin-bottom:0; }}
.msg-body ul,.msg-body ol {{ margin:8px 0 10px 20px; }}
.msg-body li {{ margin:4px 0; }}
.msg-body strong {{ color:#fff; }}
.msg-body a {{ color:var(--blue); }}
.msg-body code {{ padding:2px 5px; border-radius:4px; background:rgba(110,118,129,.28); font-size:13px; font-family:monospace; }}
.msg-body h3,.msg-body h4 {{ margin:12px 0 6px; color:#f0f6fc; }}
.msg-body blockquote {{ margin:8px 0; padding:8px 12px; border-left:3px solid var(--yellow); background:rgba(210,153,34,.08); color:#ffdf8a; }}
pre.code-block {{ margin:8px 0; padding:12px; background:#0d1117; border:1px solid var(--line); border-radius:8px; overflow:auto; font:13px/1.5 monospace; white-space:pre-wrap; }}
.empty {{ padding:48px; text-align:center; color:var(--muted); font-size:16px; }}
a {{ color:var(--blue); }}
</style>
</head>
<body>
<div class="topbar">
  <h1>🐾 Wiesel · Geflaggte Chats</h1>
  <span class="pill">{len(sessions)} Sessions</span>
  <span class="pill">{total_messages} Nachrichten</span>
  <span class="pill">{total_flags} Flags</span>
  <span class="gen">Export: {html.escape(report.get('generated_at',''))}</span>
</div>
<div class="layout">
  <div class="sidebar">{"".join(sidebar_items)}</div>
  <div class="main">
    {"".join(panels) if panels else '<div class="empty">Keine geflaggten Sessions.</div>'}
  </div>
</div>
<script>
function showSession(id) {{
  document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.sidebar-item').forEach(i => i.classList.remove('active'));
  const p = document.getElementById(id);
  if (p) p.style.display = 'flex';
  const n = document.getElementById('nav-' + id);
  if (n) n.classList.add('active');
}}
document.addEventListener('DOMContentLoaded', () => {{
  const first = document.querySelector('.sidebar-item');
  if (first) first.classList.add('active');
}});
</script>
</body>
</html>"""


def render_markdown(report: dict[str, Any], split_gaps_minutes: int = 20) -> str:
    lines = [f"# Wiesel · Geflaggte Chats · {report.get('generated_at')}", ""]
    for idx, s in enumerate(report.get("sessions", []), start=1):
        lines.append(f"## {idx}. {s.get('session_id')}")
        lines.append(f"Start: {qmark(s.get('created_at'))} · User: {qmark(s.get('user'))}")
        lines.append("")
        for m in s.get("messages", []):
            lines.append(f"**{m.get('role')}** · {m.get('created_at')}")
            lines.append("")
            lines.append(qmark(m.get("content")))
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.json:
        report = json.loads(Path(args.json).read_text(encoding="utf-8"))
        report["source"] = args.json
        report["mode"] = "json"
        report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    else:
        report = load_from_db(Path(args.db), args.days, args.include_unflagged)

    html_content = render_html(report, args.split_gaps_minutes)
    md_content = render_markdown(report, args.split_gaps_minutes)

    html_path = out_dir / "flagged-chats-latest.html"
    md_path = out_dir / "flagged-chats-latest.md"
    html_path.write_text(html_content, encoding="utf-8")
    md_path.write_text(md_content, encoding="utf-8")

    if args.archive:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        (out_dir / f"flagged-chats-{ts}.html").write_text(html_content, encoding="utf-8")
        (out_dir / f"flagged-chats-{ts}.md").write_text(md_content, encoding="utf-8")

    print(f"✅ {len(report.get('sessions', []))} geflaggte Sessions exportiert → {html_path}")

    if args.open:
        open_file(html_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())