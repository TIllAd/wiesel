"""
export_analytics.py
Täglich per Windows Task Scheduler ausführen.
Exportiert Wiesel-Chatverläufe aus wiesel.db als lesbare JSON-Datei
die Hermes direkt analysieren kann.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / "backend" / ".env")
except ImportError:
    pass

# ── Konfiguration ──────────────────────────────────────────────
DB_PATH = Path(os.getenv("WIESEL_DB_PATH", r"C:\Users\tillt\wiesel\backend\wiesel.db"))
OUTPUT_DIR = Path(os.getenv("WIESEL_ANALYTICS_DIR", str(Path(__file__).parent / "backend" / "analytics")))
TARGET_DATE = os.getenv("WIESEL_ANALYTICS_DATE")
UPDATE_DOCS = os.getenv("WIESEL_ANALYTICS_UPDATE_DOCS", "1").lower() not in {"0", "false", "no"}

# ──────────────────────────────────────────────────────────────


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None



def percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    values = sorted(values)
    idx = min(max(round((len(values) - 1) * q), 0), len(values) - 1)
    return values[idx]


def empty_usage_summary() -> dict:
    return {
        "requests_gesamt": 0,
        "requests_erfolgreich": 0,
        "requests_fehler": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_write_requests": 0,
        "tokens_gesamt": 0,
        "kosten_usd_geschaetzt": 0.0,
        "kosten_eur_geschaetzt": 0.0,
        "kosten_eur_durchschnitt_request": 0.0,
        "kosten_eur_durchschnitt_erfolgreicher_request": 0.0,
        "latenz_ms_durchschnitt": None,
        "latenz_ms_p95": None,
        "modelle": [],
    }


def usage_summary(rows: list[sqlite3.Row]) -> dict:
    if not rows:
        return empty_usage_summary()

    total_requests = len(rows)
    successful = [r for r in rows if not r["error_type"]]
    errors = [r for r in rows if r["error_type"]]
    latencies = [int(r["latency_ms"] or 0) for r in successful if r["latency_ms"] is not None]

    input_tokens = sum(int(r["input_tokens"] or 0) for r in rows)
    output_tokens = sum(int(r["output_tokens"] or 0) for r in rows)
    cache_creation = sum(int(r["cache_creation_input_tokens"] or 0) for r in rows)
    cache_read = sum(int(r["cache_read_input_tokens"] or 0) for r in rows)
    cache_write_requests = sum(1 for r in rows if int(r["cache_creation_input_tokens"] or 0) > 0)
    total_cost_usd = sum(float(r["estimated_cost_usd"] or 0) for r in rows)
    total_cost_eur = sum(float(r["estimated_cost_eur"] or 0) for r in rows)

    return {
        "requests_gesamt": total_requests,
        "requests_erfolgreich": len(successful),
        "requests_fehler": len(errors),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
        "cache_write_requests": cache_write_requests,
        "tokens_gesamt": input_tokens + output_tokens + cache_creation + cache_read,
        "kosten_usd_geschaetzt": round(total_cost_usd, 6),
        "kosten_eur_geschaetzt": round(total_cost_eur, 6),
        "kosten_eur_durchschnitt_request": round(total_cost_eur / total_requests, 6),
        "kosten_eur_durchschnitt_erfolgreicher_request": round(total_cost_eur / len(successful), 6) if successful else 0.0,
        "latenz_ms_durchschnitt": round(sum(latencies) / len(latencies)) if latencies else None,
        "latenz_ms_p95": percentile(latencies, 0.95),
        "modelle": sorted({r["model"] for r in rows if r["model"]}),
    }


def export():
    target_day = datetime.fromisoformat(TARGET_DATE).date() if TARGET_DATE else datetime.now().date()
    day_start = datetime.combine(target_day, datetime.min.time())
    day_end_exclusive = day_start + timedelta(days=1)
    day_start_iso = day_start.isoformat(sep=" ")
    day_end_exclusive_iso = day_end_exclusive.isoformat(sep=" ")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # ── Sessions laden ──
    has_chat_flags = table_exists(conn, "chat_flags")
    has_llm_usage = table_exists(conn, "llm_usage")
    sessions_rows = conn.execute("""
        SELECT * FROM sessions
        WHERE created_at >= ? AND created_at < ?
          AND EXISTS (
              SELECT 1
              FROM chat_messages
              WHERE chat_messages.session_id = sessions.id
          )
        ORDER BY created_at ASC
    """, (day_start_iso, day_end_exclusive_iso)).fetchall()

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
        """, (s["id"],)).fetchall() if has_chat_flags else []
        session_flags = [{"tag": f["tag"], "created_at": f["created_at"]} for f in flags]

        usage_rows = conn.execute("""
            SELECT model, input_tokens, output_tokens, cache_creation_input_tokens,
                   cache_read_input_tokens, estimated_cost_usd, estimated_cost_eur,
                   latency_ms, error_type, created_at
            FROM llm_usage
            WHERE session_id = ? AND created_at >= ? AND created_at < ?
            ORDER BY created_at ASC
        """, (s["id"], day_start_iso, day_end_exclusive_iso)).fetchall() if has_llm_usage else []

        verlauf = []
        msgs = [dict(m) for m in messages]
        i = 0
        while i < len(msgs):
            if msgs[i]["role"] == "user":
                frage = msgs[i]
                antwort = msgs[i + 1] if i + 1 < len(msgs) and msgs[i + 1]["role"] == "assistant" else None
                verlauf.append({
                    "zeitpunkt": frage["created_at"],
                    "frage": frage["content"],
                    "antwort": antwort["content"] if antwort else "–",
                })
                i += 2
            else:
                i += 1

        sessions.append({
            "session_id": s["id"],
            "user": s["user_name"] or "anonym",
            "kurs": s["course_name"] or "–",
            "gestartet_am": s["created_at"],
            "flags": session_flags,
            "nachrichten": len(verlauf),
            "llm_usage": usage_summary(usage_rows),
            "verlauf": verlauf,
        })

    total_messages = sum(s["nachrichten"] for s in sessions)
    all_usage_rows = conn.execute("""
        SELECT model, input_tokens, output_tokens, cache_creation_input_tokens,
               cache_read_input_tokens, estimated_cost_usd, estimated_cost_eur,
               latency_ms, error_type, created_at
        FROM llm_usage
        WHERE created_at >= ? AND created_at < ?
        ORDER BY created_at ASC
    """, (day_start_iso, day_end_exclusive_iso)).fetchall() if has_llm_usage else []

    conn.close()

    usage = usage_summary(all_usage_rows)

    output = {
        "exported_at": datetime.now().isoformat(),
        "periode": f"Tagesexport {target_day.isoformat()}",
        "statistik": {
            "sessions_gesamt": len(sessions),
            "nachrichten_gesamt": total_messages,
            "durchschnitt_pro_session": round(total_messages / len(sessions), 1) if sessions else 0,
        },
        "llm_usage": usage,
        "sessions": sessions,
    }

    # ── JSON Export ──
    filename = f"analytics_{target_day.isoformat()}.json"
    out_path = OUTPUT_DIR / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if UPDATE_DOCS:
        # ── analytics_latest.json in backend/static/docs/internal/ für schnellen Erstaufruf ──
        # Historische Tagesdateien bleiben ausschließlich in OUTPUT_DIR/WIESEL_ANALYTICS_DIR.
        docs_internal_dir = Path(__file__).parent / "backend" / "static" / "docs" / "internal"
        docs_internal_dir.mkdir(parents=True, exist_ok=True)
        docs_json = docs_internal_dir / "analytics_latest.json"
        with open(docs_json, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  analytics_latest.json → {docs_json}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Export fertig: {out_path}")
    print(f"  {len(sessions)} Sessions | {total_messages} Nachrichten | Tagesexport: {target_day.isoformat()}")


if __name__ == "__main__":
    export()
