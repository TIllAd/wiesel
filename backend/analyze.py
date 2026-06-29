"""
Wiesel Daily Analysis Script (later done by Hermes via Cronjob)
Fetches /api/logs/daily, analyses chat data, writes reports/YYYY-MM-DD.md,
and sends a short email summary via SMTP with combined HTML report attached.

Usage:
    python analyze.py               # analyse today
    python analyze.py 2026-06-24    # analyse specific date
"""

import os
import sys
import json
import smtplib
import re
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, date, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
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
HTML_TEMPLATE = Path(__file__).parent.parent / "docs" / "cost-cache-model.html"


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


# ── Language & Topic detection ───────────────────────────────────────────────
LANG_PATTERNS = {
    "de": re.compile(r"\b(ich|du|was|wie|wo|wer|bitte|danke|und|oder|ist|bin|habe|kann)\b", re.I),
    "en": re.compile(r"\b(what|where|who|how|please|thank|and|or|is|am|have|can|the)\b", re.I),
    "ar": re.compile(r"[\u0600-\u06FF]"),
    "zh": re.compile(r"[\u4e00-\u9fff]"),
}
def detect_language(text):
    scores = {lang: len(pat.findall(text)) for lang, pat in LANG_PATTERNS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"

TOPICS = {
    "Campo":         re.compile(r"\bcampo\b", re.I),
    "StudOn":        re.compile(r"\bstudon\b", re.I),
    "IDm":           re.compile(r"\bidm\b|\bidentit", re.I),
    "BAföG":         re.compile(r"\bbaf.g\b", re.I),
    "Prüfungsamt":   re.compile(r"\bpr.fungs|klausur|abmeld|attest|r.cktritt", re.I),
    "FAUcard":       re.compile(r"\bfaucard\b|\bkarte\b|\bvalidier", re.I),
    "Mensa":         re.compile(r"\bmensa\b", re.I),
    "O-Woche":       re.compile(r"\bo-woche\b|\berstwoche\b|\borientierung", re.I),
    "Bibliothek":    re.compile(r"\bbibliothek\b|\bwiso-bib\b|\bausleihen\b", re.I),
    "Überforderung": re.compile(r"\büberford|nicht mehr|aufhören|ich weiß nicht|angst", re.I),
    "Modulhandbuch": re.compile(r"\bmodul\b|\bpflichtfach\b|\bwahlpflicht\b", re.I),
    "Wer bist du":   re.compile(r"\bwer bist du\b|\bwas bist du\b", re.I),
}
def classify_topics(text):
    return [name for name, pat in TOPICS.items() if pat.search(text)]

FLAG_ICONS  = {"auffaelligkeit": "⚠️"}
FLAG_LABELS = {"auffaelligkeit": "Auffälligkeit"}


# ── Main analysis ─────────────────────────────────────────────────────────────
def analyse(target_date):
    url = f"{API_BASE}/api/logs/daily?date={target_date}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    llm_usage, llm_usage_by_session = load_llm_usage_for_day(target_date)

    sessions  = data["sessions"]
    all_msgs  = [m for sdata in sessions.values() for m in sdata["messages"]]
    user_msgs = [m for m in all_msgs if m["role"] == "user"]
    bot_msgs  = [m for m in all_msgs if m["role"] == "assistant"]

    lang_counter  = Counter(detect_language(m["content"]) for m in user_msgs)
    topic_counter = Counter()
    for m in user_msgs:
        for t in classify_topics(m["content"]):
            topic_counter[t] += 1

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
        "total_messages":   data["total_messages"],
        "total_sessions":   data["total_sessions"],
        "user_messages":    len(user_msgs),
        "bot_messages":     len(bot_msgs),
        "avg_session_len":  avg_len,
        "languages":        dict(lang_counter.most_common()),
        "topics":           dict(topic_counter.most_common(10)),
        "flagged_sessions": flagged_sessions,
        "llm_usage":        llm_usage,
    }


# ── Combined HTML Report ──────────────────────────────────────────────────────
def build_combined_html(result, target_date):
    import html as htmllib

    usage    = result["llm_usage"]
    flagged  = result["flagged_sessions"]
    # Inject into cost template if available
    cost_section = ""
    if HTML_TEMPLATE.exists():
        analytics_data = {
            "exported_at": datetime.now().isoformat(),
            "periode": f"Tagesbericht {target_date}",
            "statistik": {"sessions_gesamt": result["total_sessions"], "nachrichten_gesamt": result["total_messages"], "durchschnitt_pro_session": result["avg_session_len"]},
            "llm_usage": {**usage, "kosten_eur_geschaetzt": usage["estimated_cost_eur"], "kosten_usd_geschaetzt": usage["estimated_cost_usd"], "kosten_eur_durchschnitt_erfolgreicher_request": usage["avg_cost_eur_per_successful_request"], "modelle": usage["models"]},
            "sessions": [],
        }
        cost_section = HTML_TEMPLATE.read_text(encoding="utf-8").replace("__ANALYTICS_DATA__", json.dumps(analytics_data, ensure_ascii=False))
        # strip html/head/body wrapper to embed inline
        cost_section = re.sub(r'<!doctype[^>]*>|<html[^>]*>|</html>|<head>.*?</head>|<body[^>]*>|</body>', '', cost_section, flags=re.DOTALL|re.IGNORECASE).strip()

    # Build flagged chats section with sidebar
    def render_msg(m):
        role    = m.get("role","")
        cnt     = htmllib.escape(str(m.get("content","") or ""))
        ts      = (m.get("created_at") or "")[:16].replace("T"," ")
        label   = "🎓 Student" if role == "user" else "🐾 Wiesel"
        cls     = "msg-user" if role == "user" else "msg-assistant"
        cnt = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', cnt)
        cnt = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2" target="_blank">\1</a>', cnt)
        cnt = cnt.replace('\n', '<br>')
        return f"<div class='msg {cls}'><div class='msg-meta'>{label} · {htmllib.escape(ts)}</div><div class='msg-body'>{cnt}</div></div>"

    sidebar_items = ""
    panels = ""
    for idx, s in enumerate(flagged, start=1):
        first_user = next((m.get("content","") for m in s.get("messages",[]) if m.get("role")=="user"), "")
        preview = htmllib.escape(first_user[:60] + ("…" if len(first_user)>60 else ""))
        msgs_html = "".join(render_msg(m) for m in s.get("messages", []))
        display = "flex" if idx == 1 else "none"
        sidebar_items += f"""<div class='si' id='nav-s{idx}' onclick="showChat('s{idx}')" >
          <div class='si-num'>#{idx}</div>
          <div class='si-body'>
            <div class='si-flag'>⚠️ {htmllib.escape(s["flag_label"])} · {htmllib.escape(s["flagged_at"])} Uhr</div>
            <div class='si-msgs'>{s["message_count"]} Nachrichten</div>
            <div class='si-preview'>{preview}</div>
          </div>
        </div>"""
        panels += f"<div class='panel' id='s{idx}' style='display:{display}'><div class='chat-body'>{msgs_html}</div></div>"

    if flagged:
        flagged_section = f"""
    <div class='section'>
      <h2>🚩 Geflaggte Sessions ({len(flagged)})</h2>
      <div class='chat-layout'>
        <div class='chat-sidebar'>{sidebar_items}</div>
        <div class='chat-main'>{panels}</div>
      </div>
    </div>"""
    else:
        flagged_section = "<div class='section'><h2>🚩 Geflaggte Sessions</h2><p class='muted'>Keine.</p></div>"

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Wiesel Bericht {target_date}</title>
<style>
:root {{ --bg:#0d1117; --card:#161b22; --line:#30363d; --text:#e6edf3; --muted:#8b949e; --blue:#58a6ff; --yellow:#d29922; --flag:#e3b341; --user-bg:#0d2137; --user-border:#1f4a73; --bot-bg:#1c2128; --bot-border:#30363d; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:var(--bg); color:var(--text); font:15px/1.6 system-ui,sans-serif; padding:32px; max-width:960px; margin:0 auto; }}
h1 {{ font-size:26px; margin-bottom:6px; }}
h2 {{ font-size:19px; margin:32px 0 16px; border-bottom:1px solid var(--line); padding-bottom:8px; }}
.muted {{ color:var(--muted); font-size:13px; }}
.section {{ margin-bottom:48px; }}
.chat-card {{ border:1px solid rgba(210,153,34,.4); border-radius:12px; overflow:hidden; margin-bottom:20px; }}
.chat-header {{ background:rgba(210,153,34,.12); padding:12px 16px; font-weight:600; color:var(--flag); font-size:14px; }}
.chat-body {{ padding:16px; display:flex; flex-direction:column; gap:12px; }}
.msg {{ border-radius:10px; max-width:80%; overflow:hidden; }}
.msg-user {{ background:var(--user-bg); border:1px solid var(--user-border); align-self:flex-end; }}
.msg-assistant {{ background:var(--bot-bg); border:1px solid var(--bot-border); align-self:flex-start; }}
.msg-meta {{ padding:6px 12px; font-size:11px; color:var(--muted); border-bottom:1px solid var(--line); }}
.msg-body {{ padding:10px 14px; font-size:14px; word-break:break-word; }}
.msg-body strong {{ color:#fff; }}
.msg-body a {{ color:var(--blue); }}
a {{ color:var(--blue); }}
.chat-layout {{ display:flex; height:600px; border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
.chat-sidebar {{ width:260px; flex-shrink:0; background:#0d1117; border-right:1px solid var(--line); overflow-y:auto; }}
.si {{ padding:12px 14px; border-bottom:1px solid var(--line); cursor:pointer; display:flex; gap:8px; transition:background .15s; }}
.si:hover {{ background:rgba(255,255,255,.04); }}
.si.active {{ background:rgba(88,166,255,.1); border-left:3px solid #58a6ff; padding-left:11px; }}
.si-num {{ color:var(--muted); font-size:12px; font-weight:600; width:20px; flex-shrink:0; }}
.si-body {{ flex:1; min-width:0; }}
.si-flag {{ font-size:12px; font-weight:600; color:var(--flag); }}
.si-msgs {{ font-size:11px; color:var(--muted); margin-top:2px; }}
.si-preview {{ font-size:12px; color:var(--muted); margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.chat-main {{ flex:1; overflow:hidden; }}
.panel {{ flex-direction:column; height:100%; overflow-y:auto; }}
.chat-body {{ padding:16px; display:flex; flex-direction:column; gap:12px; }}
</style>
<script>
function showChat(id) {{
  document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.si').forEach(i => i.classList.remove('active'));
  const p = document.getElementById(id);
  if (p) p.style.display = 'flex';
  const n = document.getElementById('nav-' + id);
  if (n) n.classList.add('active');
}}
document.addEventListener('DOMContentLoaded', () => {{
  const first = document.querySelector('.si');
  if (first) first.classList.add('active');
}});
</script>
</head>
<body>
<h1>🐾 Wiesel Tagesbericht — {target_date}</h1>
<p class='muted'>Generiert: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC</p>

{flagged_section}


</body>
</html>"""


# ── Markdown Report ───────────────────────────────────────────────────────────
def build_report(r):
    usage = r["llm_usage"]
    top_topics = "\n".join(f"- **{t}**: {c} Nachrichten" for t, c in r["topics"].items()) or "- (keine)"
    lang_dist  = ", ".join(f"{l.upper()}: {c}" for l, c in r["languages"].items()) or "keine Daten"
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

## Sprachverteilung

{lang_dist}

## Häufigste Themen

{top_topics}

{flagged_section}
---
*Generiert automatisch von Wiesel analyze.py · {ts} UTC*
"""


# ── Email ─────────────────────────────────────────────────────────────────────
def send_email(subject, body, html_attachment=None, attachment_name="bericht.html"):
    if not REPORT_EMAIL or not SMTP_USER or not SMTP_PASS:
        print("⚠ E-Mail-Config unvollständig – kein Versand.")
        return
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    recipients = [r.strip() for r in REPORT_EMAIL.split(",")]
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_attachment:
        part = MIMEBase("text", "html")
        part.set_payload(html_attachment.encode("utf-8"))
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=attachment_name)
        msg.attach(part)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo(); smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.sendmail(SMTP_USER, recipients, msg.as_string())
    print(f"✉ Report gesendet an {REPORT_EMAIL}" + (" (+ HTML-Anhang)" if html_attachment else ""))


def bar(count, max_count, width=10):
    filled = round((count / max_count) * width) if max_count > 0 else 0
    return "█" * filled + "░" * (width - filled)


def email_summary(r):
    flagged = r["flagged_sessions"]
    usage   = r["llm_usage"]

    if len(flagged) == 0:   amp = "🟢  KEIN HANDLUNGSBEDARF"
    elif len(flagged) == 1: amp = "🟡  EINE AUFFÄLLIGKEIT — bitte prüfen"
    else:                   amp = f"🔴  {len(flagged)} AUFFÄLLIGKEITEN — bitte prüfen"

    lang_total  = sum(r["languages"].values()) or 1
    lang_lines  = "\n".join(f"  {l.upper():<6} {bar(c, lang_total)}  {round(c/lang_total*100)}%" for l, c in r["languages"].items())
    topic_max   = max(r["topics"].values()) if r["topics"] else 1
    topic_lines = "\n".join(f"  {n:<16} {bar(c, topic_max)}  {c}x" for n, c in list(r["topics"].items())[:5]) or "  (keine)"

    if flagged:
        flag_block = f"🚩  {len(flagged)} GEFLAGGTE SESSION(S)\n"
        for f in flagged:
            flag_block += f"  {f['icon']} {f['flag_label']}  •  {f['flagged_at']}  •  {f['message_count']} Msgs\n"
    else:
        flag_block = "🚩  Keine geflaggten Sessions\n"

    cache_hits = round(usage['cache_read_input_tokens'] / usage['cache_creation_input_tokens'], 1) if usage['cache_creation_input_tokens'] else 0
    usage_block = (
        f"HEUTE — KOSTEN & NUTZUNG\n"
        f"  Sitzungen          {r['total_sessions']}\n"
        f"  Anfragen           {r['total_messages']}  (Ø {usage['avg_cost_eur_per_successful_request']*100:.2f} ct/Anfrage)\n"
        f"  Kosten heute       {usage['estimated_cost_eur']:.4f} €\n\n"
        f"  Wissensbasis laden  {usage['cache_creation_input_tokens']:,} Tokens  →  {usage['estimated_cost_eur'] * (usage['cache_creation_input_tokens'] / max(usage['tokens_total'],1)):.4f} €\n"
        f"  Cache-Hits          {cache_hits}x  ({usage['cache_read_input_tokens']:,} Tokens)  →  günstiger Abruf\n"
        f"  Eigentlicher Input  {usage['input_tokens']:,} Tokens  (Nutzerfragen)\n"
        f"  Output              {usage['output_tokens']:,} Tokens  (Wiesel-Antworten)\n"
        f"  Fehler              {usage['requests_error']}\n"
    )

    github_url = f"https://github.com/TIllAd/wiesel/blob/main/reports/{r['date']}.md"
    docs_url   = "https://docs.chatbot-wiso.de/cost-cache-model.html"

    return (
        f"╔══════════════════════════════════════════╗\n"
        f"║  🐾 WIESEL TAGESBERICHT  {r['date']}  ║\n"
        f"╚══════════════════════════════════════════╝\n\n"
        f"{amp}\n\n"
        f"  Sessions      {r['total_sessions']}\n"
        f"  Nachrichten   {r['total_messages']}  (Ø {r['avg_session_len']}/Session)\n"
        f"  Flags         {len(flagged)}\n\n"
        f"{usage_block}\n"
        f"SPRACHEN\n{lang_lines}\n\n"
        f"THEMEN\n{topic_lines}\n\n"
        f"──────────────────────────────────────────\n"
        f"{flag_block}\n"
        f"══════════════════════════════════════════\n"
        f"📊 Kostenbericht (interaktiv): {docs_url}\n"
        f"📎 Detaillierter Bericht (Chats + Kosten) im Anhang\n"
        f"🔗 {github_url}\n"
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

    # analytics_latest.json für Webserver
    docs_json = Path(__file__).parent.parent / "docs" / "analytics_latest.json"
    try:
        with open(docs_json, "w", encoding="utf-8") as f:
            json.dump({
                "exported_at": datetime.now().isoformat(),
                "periode": f"Tagesbericht {target}",
                "statistik": {"sessions_gesamt": result["total_sessions"], "nachrichten_gesamt": result["total_messages"], "durchschnitt_pro_session": result["avg_session_len"]},
                "llm_usage": {**result["llm_usage"], "kosten_eur_geschaetzt": result["llm_usage"]["estimated_cost_eur"], "kosten_usd_geschaetzt": result["llm_usage"]["estimated_cost_usd"], "kosten_eur_durchschnitt_erfolgreicher_request": result["llm_usage"]["avg_cost_eur_per_successful_request"], "modelle": result["llm_usage"]["models"], "cache_write_requests": result["llm_usage"]["cache_write_requests"]},
                "sessions": [],
            }, f, ensure_ascii=False, indent=2)
        print(f"✅ analytics_latest.json aktualisiert")
    except Exception as e:
        print(f"⚠ analytics_latest.json fehlgeschlagen: {e}")

    html = build_combined_html(result, target)
    send_email(
        subject=f"[Wiesel] Tagesbericht {target}",
        body=email_summary(result),
        html_attachment=html,
        attachment_name=f"bericht_{target}.html",
    )