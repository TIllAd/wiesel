"""
Wiesel Daily Analysis Script (later done by Hermes via Cronjob)
Fetches /api/logs/daily, analyses chat data, writes reports/YYYY-MM-DD.md,
and sends a short plain-text email summary via SMTP.

Usage:
    python analyze.py               # analyse today
    python analyze.py 2026-06-24    # analyse specific date
"""

import os
import sys
import json
import smtplib
import sqlite3
import subprocess
from datetime import datetime, date, timezone
from email.message import EmailMessage
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

# ── Config ───────────────────────────────────────────────────────────────────
API_BASE      = os.getenv("WIESEL_API_BASE", "http://localhost:8001")
REPORT_EMAIL  = os.getenv("REPORT_EMAIL", "")
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASS     = os.getenv("SMTP_PASS", "")
REPO_ROOT     = Path(__file__).parent.parent
REPORTS_DIR   = REPO_ROOT / "reports"
DB_PATH       = Path(os.getenv("WIESEL_DB_PATH", str(Path(__file__).parent / "wiesel.db")))


# ── LLM Usage from SQLite ────────────────────────────────────────────────────
def table_exists(conn, name):
    return conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

def percentile(values, p):
    if not values: return None
    idx = max(0, min(len(values) - 1, round((len(values) - 1) * p)))
    return sorted(values)[idx]

def empty_usage_summary():
    return {"requests_total":0,"requests_successful":0,"requests_error":0,"input_tokens":0,"output_tokens":0,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"cache_write_requests":0,"tokens_total":0,"estimated_cost_usd":0.0,"estimated_cost_eur":0.0,"avg_cost_eur_per_request":0.0,"avg_cost_eur_per_successful_request":0.0,"latency_ms_avg":None,"latency_ms_p95":None,"models":[]}

def usage_summary(rows):
    if not rows: return empty_usage_summary()
    successful = [r for r in rows if not r["error_type"]]
    latencies  = [int(r["latency_ms"] or 0) for r in successful if r["latency_ms"] is not None]
    input_tok  = sum(int(r["input_tokens"] or 0) for r in rows)
    output_tok = sum(int(r["output_tokens"] or 0) for r in rows)
    cache_cre  = sum(int(r["cache_creation_input_tokens"] or 0) for r in rows)
    cache_read = sum(int(r["cache_read_input_tokens"] or 0) for r in rows)
    cache_write_requests = sum(1 for r in rows if int(r["cache_creation_input_tokens"] or 0) > 0)
    cost_usd   = sum(float(r["estimated_cost_usd"] or 0) for r in rows)
    cost_eur   = sum(float(r["estimated_cost_eur"] or 0) for r in rows)
    total      = len(rows)
    return {
        "requests_total": total, "requests_successful": len(successful), "requests_error": len(rows)-len(successful),
        "input_tokens": input_tok, "output_tokens": output_tok,
        "cache_creation_input_tokens": cache_cre, "cache_read_input_tokens": cache_read,
        "cache_write_requests": cache_write_requests,
        "tokens_total": input_tok+output_tok+cache_cre+cache_read,
        "estimated_cost_usd": round(cost_usd,6), "estimated_cost_eur": round(cost_eur,6),
        "avg_cost_eur_per_request": round(cost_eur/total,6) if total else 0.0,
        "avg_cost_eur_per_successful_request": round(cost_eur/len(successful),6) if successful else 0.0,
        "latency_ms_avg": round(sum(latencies)/len(latencies)) if latencies else None,
        "latency_ms_p95": percentile(latencies, 0.95),
        "models": sorted({r["model"] for r in rows if r["model"]}),
    }

def load_llm_usage_for_day(target_date):
    if not DB_PATH.exists(): return empty_usage_summary(), {}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "llm_usage"): return empty_usage_summary(), {}
        rows = conn.execute("""
            SELECT session_id, model, input_tokens, output_tokens,
                   cache_creation_input_tokens, cache_read_input_tokens,
                   estimated_cost_usd, estimated_cost_eur, latency_ms,
                   error_type, created_at
            FROM llm_usage WHERE date(created_at) = date(?) ORDER BY created_at ASC
        """, (target_date,)).fetchall()
        rows_by_session = {}
        for row in rows:
            rows_by_session.setdefault(row["session_id"], []).append(row)
        return usage_summary(rows), {sid: usage_summary(srows) for sid, srows in rows_by_session.items()}
    finally:
        conn.close()


FLAG_ICONS  = {"auffaelligkeit": "⚠️"}
FLAG_LABELS = {"auffaelligkeit": "Auffälligkeit"}


# ── Main analysis ─────────────────────────────────────────────────────────────
def analyse(target_date):
    url = f"{API_BASE}/api/logs/daily?date={target_date}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    llm_usage, llm_usage_by_session = load_llm_usage_for_day(target_date)

    sessions  = {
        sid: sdata
        for sid, sdata in data["sessions"].items()
        if sdata.get("messages")
    }
    all_msgs  = [m for sdata in sessions.values() for m in sdata["messages"]]
    user_msgs = [m for m in all_msgs if m["role"] == "user"]
    bot_msgs  = [m for m in all_msgs if m["role"] == "assistant"]

    session_lengths = [len(sdata["messages"]) for sdata in sessions.values()]
    avg_len = round(sum(session_lengths) / len(session_lengths), 1) if session_lengths else 0

    flagged_sessions = [
        {
            "session_id":    sid,
            "flag_type":     sdata["flags"][0]["tag"],
            "flag_label":    FLAG_LABELS.get(sdata["flags"][0]["tag"], sdata["flags"][0]["tag"]),
            "icon":          FLAG_ICONS.get(sdata["flags"][0]["tag"], "🚩"),
            "flagged_at":    sdata["flags"][0]["created_at"][11:16],
            "message_count": len(sdata["messages"]),
            "messages":      sdata["messages"],
            "llm_usage":     llm_usage_by_session.get(sid, empty_usage_summary()),
        }
        for sid, sdata in sessions.items()
        if sdata.get("flags")
    ]

    return {
        "date":             target_date,
        "total_messages":   len(all_msgs),
        "total_sessions":   len(sessions),
        "user_messages":    len(user_msgs),
        "bot_messages":     len(bot_msgs),
        "avg_session_len":  avg_len,
        "flagged_sessions": flagged_sessions,
        "llm_usage":        llm_usage,
    }



# ── Markdown Report ───────────────────────────────────────────────────────────
def build_report(r):
    usage = r["llm_usage"]
    if r["flagged_sessions"]:
        rows = "\n".join(f"- {f['icon']} **{f['flag_label']}** — `{f['session_id'][:20]}...` ({f['message_count']} Msgs) — {f['flagged_at']} Uhr" for f in r["flagged_sessions"])
        flagged_section = f"## 🚩 Geflaggte Sessions ({len(r['flagged_sessions'])})\n\n{rows}\n"
    else:
        flagged_section = "## 🚩 Geflaggte Sessions\n\n- keine\n"
    models = ", ".join(usage["models"]) or "–"
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    return f"""# Wiesel Tagesbericht – {r['date']}

## Übersicht

| Metrik | Wert |
|--------|------|
| Nachrichten gesamt | {r['total_messages']} |
| Davon User | {r['user_messages']} |
| Davon Wiesel | {r['bot_messages']} |
| Sessions | {r['total_sessions']} |
| Ø Nachrichten/Session | {r['avg_session_len']} |
| Geflaggte Sessions | {len(r['flagged_sessions'])} |

## LLM Usage & Kosten

| Metrik | Wert |
|--------|------|
| LLM-Requests gesamt | {usage['requests_total']} |
| Erfolgreich / Fehler | {usage['requests_successful']} / {usage['requests_error']} |
| Input Tokens | {usage['input_tokens']:,} |
| Output Tokens | {usage['output_tokens']:,} |
| Cache Write Tokens | {usage['cache_creation_input_tokens']:,} |
| Cache Read Tokens | {usage['cache_read_input_tokens']:,} |
| Kosten geschätzt | {usage['estimated_cost_eur']:.6f} € ({usage['estimated_cost_usd']:.6f} $) |
| Ø Kosten / Request | {usage['avg_cost_eur_per_successful_request']:.6f} € |
| Latenz Ø / P95 | {usage['latency_ms_avg']} ms / {usage['latency_ms_p95']} ms |
| Modelle | {models} |

{flagged_section}
---
*Generiert automatisch von Wiesel analyze.py · {ts} UTC*
"""


# ── Email ─────────────────────────────────────────────────────────────────────
def send_email(subject, body):
    if not REPORT_EMAIL or not SMTP_USER or not SMTP_PASS:
        print("⚠ E-Mail-Config unvollständig – kein Versand.")
        print("--- Mail-Vorschau ---")
        print(f"Subject: {subject}")
        print(body)
        return

    recipients = [r.strip() for r in REPORT_EMAIL.split(",") if r.strip()]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg.set_content(body, subtype="plain", charset="utf-8")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo(); smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)
    print(f"✉ Report gesendet an {REPORT_EMAIL}")


def ampel(flag_count):
    if flag_count == 0:
        return "🟢", "KEIN HANDLUNGSBEDARF", "0 Auffälligkeiten"
    if flag_count == 1:
        return "🟡", "EINE AUFFÄLLIGKEIT — bitte prüfen", "eine Auffälligkeit"
    return "🔴", f"{flag_count} AUFFÄLLIGKEITEN — bitte prüfen", f"{flag_count} Auffälligkeiten"


def email_subject(r):
    icon, _, auffaelligkeiten = ampel(len(r["flagged_sessions"]))
    return f"[Wiesel] {icon} {r['date']} — {auffaelligkeiten}"


def email_summary(r):
    usage = r["llm_usage"]
    icon, text, _ = ampel(len(r["flagged_sessions"]))
    report_url = f"https://docs.chatbot-wiso.de/internal/reports.html#{r['date']}"
    docs_url = "https://docs.chatbot-wiso.de/internal/"

    return (
        f"{icon} {text}\n\n"
        f"  Sessions      {r['total_sessions']}\n"
        f"  Nachrichten   {r['total_messages']}  (Ø {r['avg_session_len']}/Session)\n"
        f"  Kosten heute  {usage['estimated_cost_eur']:.4f} €\n\n"
        f"📊 Tagesbericht:  {report_url}\n"
        f"🏠 Alle Docs:     {docs_url}\n"
    )


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    print(f"📊 Analysiere Wiesel-Chats für {target} ...")
    result = analyse(target)

    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"{target}.md"
    report_path.write_text(build_report(result), encoding="utf-8")
    print(f"✅ Report geschrieben: {report_path}")

    try:
        repo_root = Path(__file__).parent.parent
        subprocess.run(["git", "add", "-f", f"reports/{target}.md"], cwd=repo_root, check=True)
        r = subprocess.run(["git", "commit", "-m", f"report: {target}"], cwd=repo_root)
        if r.returncode == 0:
            subprocess.run(["git", "push"], cwd=repo_root, check=True)
            print(f"✅ Report gepusht: reports/{target}.md")
        else:
            print("ℹ Report unverändert – kein Push nötig.")
    except subprocess.CalledProcessError as e:
        print(f"⚠ Git push fehlgeschlagen: {e}")

    # analytics_latest.json für schnellen Erstaufruf; historische Tagesdateien liegen in WIESEL_ANALYTICS_DIR.
    docs_internal_dir = Path(__file__).parent / "static" / "docs" / "internal"
    docs_json = docs_internal_dir / "analytics_latest.json"
    try:
        payload = {
            "exported_at": datetime.now().isoformat(),
            "periode": f"Tagesbericht {target}",
            "statistik": {"sessions_gesamt": result["total_sessions"], "nachrichten_gesamt": result["total_messages"], "durchschnitt_pro_session": result["avg_session_len"]},
            "llm_usage": {**result["llm_usage"], "kosten_eur_geschaetzt": result["llm_usage"]["estimated_cost_eur"], "kosten_usd_geschaetzt": result["llm_usage"]["estimated_cost_usd"], "kosten_eur_durchschnitt_erfolgreicher_request": result["llm_usage"]["avg_cost_eur_per_successful_request"], "modelle": result["llm_usage"]["models"], "cache_write_requests": result["llm_usage"]["cache_write_requests"]},
            "sessions": [],
        }
        docs_internal_dir.mkdir(parents=True, exist_ok=True)
        with open(docs_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"✅ analytics_latest.json aktualisiert")
    except Exception as e:
        print(f"⚠ analytics JSON fehlgeschlagen: {e}")

    send_email(
        subject=email_subject(result),
        body=email_summary(result),
    )