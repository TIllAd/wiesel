"""
export_analytics.py
Wöchentlich per Windows Task Scheduler ausführen (z.B. Montag 08:00 Uhr).
Exportiert Wiesel-Chatverläufe aus wiesel.db als lesbare JSON-Datei
die Hermes direkt analysieren kann.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

# ── Konfiguration ──────────────────────────────────────────────
DB_PATH     = r"C:\Users\tillt\wiesel\backend\wiesel.db"
OUTPUT_DIR  = r"C:\Users\tillt\hermes\analytics"
DAYS_BACK   = 7
# ──────────────────────────────────────────────────────────────

def export():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    since = (datetime.now() - timedelta(days=DAYS_BACK)).isoformat()

    # ── Sessions laden ──
    sessions_rows = conn.execute("""
        SELECT * FROM sessions
        WHERE created_at >= ?
        ORDER BY created_at ASC
    """, (since,)).fetchall()

    # ── Nachrichten pro Session laden ──
    sessions = []
    for s in sessions_rows:
        messages = conn.execute("""
            SELECT id, role, content, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
        """, (s["id"],)).fetchall()
        flags = conn.execute("""
            SELECT tag, created_at
            FROM chat_flags
            WHERE session_id = ? AND message_id IS NULL
            ORDER BY created_at ASC
        """, (s["id"],)).fetchall() if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_flags'").fetchone() else []
        session_flags = [{"tag": f["tag"], "created_at": f["created_at"]} for f in flags]

        verlauf = []
        msgs = [dict(m) for m in messages]
        i = 0
        while i < len(msgs):
            if msgs[i]["role"] == "user":
                frage = msgs[i]
                antwort = msgs[i+1] if i+1 < len(msgs) and msgs[i+1]["role"] == "assistant" else None
                verlauf.append({
                    "zeitpunkt": frage["created_at"],
                    "frage":     frage["content"],
                    "antwort":   antwort["content"] if antwort else "–",
                })
                i += 2
            else:
                i += 1

        sessions.append({
            "session_id":   s["id"],
            "user":         s["user_name"] or "anonym",
            "kurs":         s["course_name"] or "–",
            "gestartet_am": s["created_at"],
            "flags":        session_flags,
            "nachrichten":  len(verlauf),
            "verlauf":      verlauf,
        })

    conn.close()

    total_messages = sum(s["nachrichten"] for s in sessions)

    output = {
        "exported_at": datetime.now().isoformat(),
        "periode": f"Letzte {DAYS_BACK} Tage (ab {since[:10]})",
        "statistik": {
            "sessions_gesamt":          len(sessions),
            "nachrichten_gesamt":       total_messages,
            "durchschnitt_pro_session": round(total_messages / len(sessions), 1) if sessions else 0,
        },
        "sessions": sessions
    }

    # Eine Datei pro Woche – kein Überschreiben
    filename = f"analytics_{datetime.now().strftime('%Y-%m-%d')}.json"
    out_path = Path(OUTPUT_DIR) / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Export fertig: {out_path}")
    print(f"  {len(sessions)} Sessions | {total_messages} Nachrichten | Periode: {since[:10]} – heute")

if __name__ == "__main__":
    export()