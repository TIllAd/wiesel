"""
export_analytics.py
Wöchentlich per Windows Task Scheduler ausführen (z.B. Montag 08:00 Uhr).
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
OUTPUT_DIR = Path(os.getenv("WIESEL_ANALYTICS_DIR", r"C:\Users\tillt\hermes\analytics"))
DAYS_BACK = int(os.getenv("WIESEL_ANALYTICS_DAYS_BACK", "7"))

# Preise aus .env (gleiche Quelle wie main.py)
INPUT_USD_PER_MTOK   = float(os.getenv("LLM_INPUT_USD_PER_MTOK",   "1.00"))
OUTPUT_USD_PER_MTOK  = float(os.getenv("LLM_OUTPUT_USD_PER_MTOK",  "5.00"))
CACHE_WRITE_USD_PER_MTOK = float(os.getenv("LLM_CACHE_WRITE_USD_PER_MTOK", "1.25"))
CACHE_READ_USD_PER_MTOK  = float(os.getenv("LLM_CACHE_READ_USD_PER_MTOK",  "0.10"))
USD_PER_EUR          = float(os.getenv("USD_PER_EUR", "1.08"))
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    since = (datetime.now() - timedelta(days=DAYS_BACK)).isoformat()

    # ── Sessions laden ──
    has_chat_flags = table_exists(conn, "chat_flags")
    has_llm_usage = table_exists(conn, "llm_usage")
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
        """, (s["id"],)).fetchall() if has_chat_flags else []
        session_flags = [{"tag": f["tag"], "created_at": f["created_at"]} for f in flags]

        usage_rows = conn.execute("""
            SELECT model, input_tokens, output_tokens, cache_creation_input_tokens,
                   cache_read_input_tokens, estimated_cost_usd, estimated_cost_eur,
                   latency_ms, error_type, created_at
            FROM llm_usage
            WHERE session_id = ?
            ORDER BY created_at ASC
        """, (s["id"],)).fetchall() if has_llm_usage else []

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
            "llm_usage":    usage_summary(usage_rows),
            "verlauf":      verlauf,
        })

    total_messages = sum(s["nachrichten"] for s in sessions)
    all_usage_rows = conn.execute("""
        SELECT model, input_tokens, output_tokens, cache_creation_input_tokens,
               cache_read_input_tokens, estimated_cost_usd, estimated_cost_eur,
               latency_ms, error_type, created_at
        FROM llm_usage
        WHERE created_at >= ?
        ORDER BY created_at ASC
    """, (since,)).fetchall() if has_llm_usage else []

    # Anfragen seit Monatsanfang für kalenderbasierte Prognose
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    msgs_since_month_start = conn.execute("""
        SELECT COUNT(*) FROM chat_messages
        WHERE role = 'user' AND created_at >= ?
    """, (month_start.isoformat(),)).fetchone()[0]

    conn.close()

    usage = usage_summary(all_usage_rows)
    reqs = usage["requests_erfolgreich"] or 1

    # ── Kostenmodell berechnen ──
    # Anzahl echter Kaltstarts (Requests mit Cache-Write > 0)
    # Verhindert dass mehrere Kaltstarts über 7 Tage als ein einziger gewertet werden
    num_coldstarts = max(sum(1 for r in all_usage_rows if int(r["cache_creation_input_tokens"] or 0) > 0), 1)
    avg_cache_write_tokens = usage["cache_creation_input_tokens"] / num_coldstarts
    cache_write_usd = (avg_cache_write_tokens / 1e6) * CACHE_WRITE_USD_PER_MTOK
    warm_per_req_usd = (
        (usage["cache_read_input_tokens"] / 1e6 / reqs) * CACHE_READ_USD_PER_MTOK
        + (usage["input_tokens"] / 1e6 / reqs) * INPUT_USD_PER_MTOK
        + (usage["output_tokens"] / 1e6 / reqs) * OUTPUT_USD_PER_MTOK
    )
    usd_eur = (
        usage["kosten_eur_geschaetzt"] / usage["kosten_usd_geschaetzt"]
        if usage["kosten_usd_geschaetzt"] else USD_PER_EUR
    )

    def cost_ct(n: int) -> float:
        return round(((cache_write_usd / n) + warm_per_req_usd) / usd_eur * 100, 4)

    # ── Monatsprognose: Anfragen seit Monatsanfang + Hochrechnung auf Monatsende ──
    import calendar
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_elapsed = max(now.day, 1)
    days_remaining = days_in_month - now.day
    msgs_per_month = msgs_since_month_start + round(msgs_since_month_start / days_elapsed * days_remaining)
    avg_ct = round(usage["kosten_eur_durchschnitt_erfolgreicher_request"] * 100, 4)

    kosten_modell = {
        "hinweis": "Berechnet aus echten Token-Daten dieses Exports. Cache-Write einmalig, dann auf Folgeanfragen verteilt.",
        "usd_eur_kurs": round(usd_eur, 4),
        "gemessen_eur": usage["kosten_eur_geschaetzt"],
        "schnitt_ct_pro_request": avg_ct,
        "warm_request_ct": round(warm_per_req_usd / usd_eur * 100, 4),
        "worst_case_ct": cost_ct(1),
        "best_case_ct": cost_ct(100),
        "preise": {
            "input_usd_per_mtok": INPUT_USD_PER_MTOK,
            "output_usd_per_mtok": OUTPUT_USD_PER_MTOK,
            "cache_write_usd_per_mtok": CACHE_WRITE_USD_PER_MTOK,
            "cache_read_usd_per_mtok": CACHE_READ_USD_PER_MTOK,
        },
        "token_basis": {
            "cache_creation_input_tokens": usage["cache_creation_input_tokens"],
            "cache_read_input_tokens": usage["cache_read_input_tokens"],
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "requests_erfolgreich": reqs,
            "num_coldstarts": num_coldstarts,
            "avg_cache_write_tokens_per_coldstart": round(avg_cache_write_tokens),
        },
        "szenarien_ct": {str(n): cost_ct(n) for n in range(1, 101)},
        "projektion_1000_requests_eur": {
            "worst":   round(cost_ct(1) * 10, 2),
            "current": round(avg_ct * 10, 2),
            "best":    round(cost_ct(100) * 10, 2),
        },
        "projektion_monat_eur": {
            "nachrichten_pro_monat": msgs_per_month,
            "nachrichten_seit_monatsanfang": msgs_since_month_start,
            "tage_vergangen": days_elapsed,
            "tage_verbleibend": days_remaining,
            "worst":   round(cost_ct(1) * msgs_per_month / 100, 2),
            "current": round(avg_ct * msgs_per_month / 100, 2),
            "best":    round(cost_ct(100) * msgs_per_month / 100, 2),
        },
    }

    output = {
        "exported_at": datetime.now().isoformat(),
        "periode": f"Letzte {DAYS_BACK} Tage (ab {since[:10]})",
        "statistik": {
            "sessions_gesamt":          len(sessions),
            "nachrichten_gesamt":       total_messages,
            "durchschnitt_pro_session": round(total_messages / len(sessions), 1) if sessions else 0,
        },
        "llm_usage": usage,
        "kosten_modell": kosten_modell,
        "sessions": sessions,
    }

    # ── JSON Export ──
    filename = f"analytics_{datetime.now().strftime('%Y-%m-%d')}.json"
    out_path = OUTPUT_DIR / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # ── analytics_latest.json in docs/ für Webserver ──
    docs_json = Path(__file__).parent / "docs" / "analytics_latest.json"
    with open(docs_json, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  analytics_latest.json → {docs_json}")

    # ── HTML Report generieren ──
    html_template = Path(__file__).parent / "docs" / "cost-cache-model.html"
    if html_template.exists():
        html = html_template.read_text(encoding="utf-8")
        html = html.replace(
            "__ANALYTICS_DATA__",
            json.dumps(output, ensure_ascii=False)
        )
        html_out = OUTPUT_DIR / f"bericht_{datetime.now().strftime('%Y-%m-%d')}.html"
        html_out.write_text(html, encoding="utf-8")
        print(f"  HTML-Bericht: {html_out}")
    else:
        print(f"  HTML-Vorlage nicht gefunden: {html_template}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Export fertig: {out_path}")
    print(f"  {len(sessions)} Sessions | {total_messages} Nachrichten | Periode: {since[:10]} – heute")

if __name__ == "__main__":
    export()