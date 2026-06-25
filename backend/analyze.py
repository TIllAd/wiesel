"""
Wiesel Daily Analysis Script
Fetches /api/logs/daily, analyses chat data, writes reports/YYYY-MM-DD.md,
and sends a short email summary via SMTP.

Usage:
    python analyze.py               # analyse today
    python analyze.py 2026-06-24    # analyse specific date
"""

import os
import sys
import json
import smtplib
import re
import subprocess
from collections import Counter
from datetime import datetime, date
from email.mime.text import MIMEText
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

# ── Config ──────────────────────────────────────────────────────────────────
API_BASE     = os.getenv("WIESEL_API_BASE", "http://localhost:8001")
REPORT_EMAIL = os.getenv("REPORT_EMAIL", "")
SMTP_HOST    = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER    = os.getenv("SMTP_USER", "")
SMTP_PASS    = os.getenv("SMTP_PASS", "")
REPO_ROOT    = Path(__file__).parent.parent
REPORTS_DIR  = REPO_ROOT / "reports"
GITHUB_REPO  = os.getenv("GITHUB_REPO", "TIllAd/wiesel")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")


# ── Language detection (simple heuristic) ───────────────────────────────────
LANG_PATTERNS = {
    "de": re.compile(r"\b(ich|du|was|wie|wo|wer|bitte|danke|und|oder|ist|bin|habe|kann)\b", re.I),
    "en": re.compile(r"\b(what|where|who|how|please|thank|and|or|is|am|have|can|the)\b", re.I),
    "ar": re.compile(r"[\u0600-\u06FF]"),
    "zh": re.compile(r"[\u4e00-\u9fff]"),
}

def detect_language(text: str) -> str:
    scores = {lang: len(pat.findall(text)) for lang, pat in LANG_PATTERNS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


# ── Topic classification (keyword-based) ────────────────────────────────────
TOPICS = {
    "Campo":          re.compile(r"\bcampo\b", re.I),
    "StudOn":         re.compile(r"\bstudon\b", re.I),
    "IDm":            re.compile(r"\bidm\b|\bidentit", re.I),
    "BAföG":          re.compile(r"\bbaf.g\b", re.I),
    "Prüfungsamt":    re.compile(r"\bpr.fungs|klausur|abmeld|attest|r.cktritt", re.I),
    "FAUcard":        re.compile(r"\bfaucard\b|\bkarte\b|\bvalidier", re.I),
    "Mensa":          re.compile(r"\bmensa\b", re.I),
    "O-Woche":        re.compile(r"\bo-woche\b|\berstwoche\b|\borientierung", re.I),
    "Bibliothek":     re.compile(r"\bbibliothek\b|\bwiso-bib\b|\bausleihen\b", re.I),
    "Überforderung":  re.compile(r"\büberford|nicht mehr|aufhören|ich weiß nicht|angst", re.I),
    "Fachinhalt":     re.compile(r"\bopportunit|mikroökon|makroökon|statistik|buchführ", re.I),
    "Modulhandbuch":  re.compile(r"\bmodul\b|\bpflichtfach\b|\bwahlpflicht\b", re.I),
    "Wer bist du":    re.compile(r"\bwer bist du\b|\bwas bist du\b", re.I),
}

def classify_topics(text: str) -> list[str]:
    return [name for name, pat in TOPICS.items() if pat.search(text)]


# ── Error detection ──────────────────────────────────────────────────────────
ERROR_PATTERNS = [
    re.compile(r"tut mir leid|leider nicht|kann ich nicht|weiß ich nicht", re.I),
    re.compile(r"error|exception|500|traceback", re.I),
    re.compile(r"ich bin nicht sicher|keine information", re.I),
]

def has_error_response(text: str) -> bool:
    return any(p.search(text) for p in ERROR_PATTERNS)
def extract_error_snippets(bot_msgs: list, max_n: int = 3) -> list[str]:
    """Return up to max_n short snippets from bot messages that look like errors."""
    snippets = []
    for m in bot_msgs:
        if has_error_response(m["content"]):
            snippets.append(m["content"][:150].replace("\n", " ").strip())
        if len(snippets) >= max_n:
            break
    return snippets

FACHINHALT_PAT = re.compile(
    r"\bopportunit|mikroökon|makroökon|statistik|buchführ|kosten(?:rechnung)?|"
    r"\bvwl\b|\bbwl\b|\bformeln?\b|\bderivat|\bintegral|marketing|management",
    re.I,
)

def extract_fachinhalt_examples(user_msgs: list, max_n: int = 3) -> list[str]:
    """Return up to max_n user messages that are clearly out-of-scope (Fachinhalt)."""
    examples = []
    for m in user_msgs:
        if FACHINHALT_PAT.search(m["content"]):
            examples.append(m["content"][:120].replace("\n", " ").strip())
        if len(examples) >= max_n:
            break
    return examples


# ── Main analysis ────────────────────────────────────────────────────────────
def analyse(target_date: str) -> dict:
    url = f"{API_BASE}/api/logs/daily?date={target_date}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    sessions   = data["sessions"]
    all_msgs   = [m for msgs in sessions.values() for m in msgs]
    user_msgs  = [m for m in all_msgs if m["role"] == "user"]
    bot_msgs   = [m for m in all_msgs if m["role"] == "assistant"]

    # Language distribution (user messages only)
    lang_counter = Counter(detect_language(m["content"]) for m in user_msgs)

    # Topic distribution
    topic_counter = Counter()
    for m in user_msgs:
        for t in classify_topics(m["content"]):
            topic_counter[t] += 1

    # Error responses (bot messages)
    error_count = sum(1 for m in bot_msgs if has_error_response(m["content"]))
    error_snippets = extract_error_snippets(bot_msgs)
    fachinhalt_examples = extract_fachinhalt_examples(user_msgs)
    # Avg messages per session
    # Avg messages per session
    session_lengths = [len(msgs) for msgs in sessions.values()]
    avg_len = round(sum(session_lengths) / len(session_lengths), 1) if session_lengths else 0

    # Uncategorised user messages
    uncategorised = [
        m["content"][:120]
        for m in user_msgs
        if not classify_topics(m["content"])
    ]

    return {
        "date":              target_date,
        "total_messages":    data["total_messages"],
        "total_sessions":    data["total_sessions"],
        "user_messages":     len(user_msgs),
        "bot_messages":      len(bot_msgs),
        "avg_session_len":   avg_len,
        "languages":         dict(lang_counter.most_common()),
        "topics":            dict(topic_counter.most_common(10)),
        "error_responses":   error_count,
        "uncategorised":     uncategorised[:10],  # top 10 for report
        "error_snippets":    error_snippets,
        "fachinhalt_examples": fachinhalt_examples,
    }


# ── Report generation ────────────────────────────────────────────────────────
def build_report(r: dict) -> str:
    top_topics = "\n".join(
        f"- **{t}**: {c} Nachrichten"
        for t, c in r["topics"].items()
    ) or "- (keine Kategorisierung möglich)"

    lang_dist = ", ".join(
        f"{lang.upper()}: {cnt}" for lang, cnt in r["languages"].items()
    ) or "keine Daten"

    uncategorised_block = "\n".join(
        f"- `{q}`" for q in r["uncategorised"]
    ) or "- keine"

    return f"""# Wiesel Tagesbericht – {r['date']}

## Übersicht

| Metrik | Wert |
|--------|------|
| Nachrichten gesamt | {r['total_messages']} |
| Davon User | {r['user_messages']} |
| Davon Wiesel | {r['bot_messages']} |
| Sessions | {r['total_sessions']} |
| Ø Nachrichten/Session | {r['avg_session_len']} |
| Fehler-Antworten (Bot) | {r['error_responses']} |

## Sprachverteilung (User-Nachrichten)

{lang_dist}

## Häufigste Themen

{top_topics}

## Nicht kategorisierte Anfragen (Stichprobe)

{uncategorised_block}

---
*Generiert automatisch von Wiesel analyze.py · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC*
"""


# ── Email ────────────────────────────────────────────────────────────────────
def send_email(subject: str, body: str):
    if not REPORT_EMAIL or not SMTP_USER or not SMTP_PASS:
        print("⚠ E-Mail-Config unvollständig (REPORT_EMAIL / SMTP_USER / SMTP_PASS) – kein Versand.")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = REPORT_EMAIL

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.sendmail(SMTP_USER, [REPORT_EMAIL], msg.as_string())
    print(f"✉ Report gesendet an {REPORT_EMAIL}")


def ampel(r: dict) -> tuple[str, str]:
    """Gibt (emoji, text) zurück basierend auf Tagesqualität."""
    errors = r["error_responses"]
    scope  = len(r["fachinhalt_examples"])
    
    if errors == 0 and scope == 0:
        return "🟢", "GUTER TAG — Wiesel hat funktioniert"
    elif errors <= 2 and scope <= 1:
        return "🟡", "OKAY — Ein paar Ausreißer, nichts Kritisches"
    else:
        return "🔴", "SCHAUEN — Wiesel braucht Aufmerksamkeit"
 
 
def bar(count: int, max_count: int, width: int = 10) -> str:
    filled = round((count / max_count) * width) if max_count > 0 else 0
    return "█" * filled + "░" * (width - filled)
 
 
def email_summary(r: dict) -> str:
    amp_emoji, amp_text = ampel(r)
    
    # Sprachen
    lang_total = sum(r["languages"].values()) or 1
    lang_lines = "\n".join(
        f"  {lang.upper():<6} {bar(cnt, lang_total)}  {round(cnt/lang_total*100)}%"
        for lang, cnt in r["languages"].items()
    )
 
    # Themen
    topic_max = max(r["topics"].values()) if r["topics"] else 1
    topic_lines = "\n".join(
        f"  {name:<16} {bar(cnt, topic_max)}  {cnt}x"
        for name, cnt in list(r["topics"].items())[:5]
    ) or "  (keine)"
 
    # Fehler-Block
    if r["error_responses"] > 0 and r["error_snippets"]:
        fehler_block = f"⚠️  {r['error_responses']} FEHLER-ANTWORT(EN)\n"
        for s in r["error_snippets"]:
            fehler_block += f'  » "{s[:80]}..."\n'
    elif r["error_responses"] > 0:
        fehler_block = f"⚠️  {r['error_responses']} Fehler-Antwort(en) — keine Snippets\n"
    else:
        fehler_block = "✅  Keine Fehler-Antworten\n"
 
    # Scope-Block
    if r["fachinhalt_examples"]:
        scope_block = f"🚨  {len(r['fachinhalt_examples'])} SCOPE-BRUCH (Fachinhalt)\n"
        for e in r["fachinhalt_examples"]:
            scope_block += f'  » "{e[:80]}"\n'
    else:
        scope_block = "✅  Keine Scope-Brüche\n"
 
    github_url = f"https://github.com/TIllAd/wiesel/blob/main/reports/{r['date']}.md"
 
    return f"""╔══════════════════════════════════════════╗
║  🐾 WIESEL TAGESBERICHT  {r['date']}  ║
╚══════════════════════════════════════════╝
 
{amp_emoji} {amp_text}
 
┌──────────────────────────────────────────┐
│  Sessions      {r['total_sessions']:<6}                    │
│  Nachrichten   {r['total_messages']:<6}  (Ø {r['avg_session_len']}/Session)     │
│  Fehler        {r['error_responses']:<6}                    │
│  Scope-Brüche  {len(r['fachinhalt_examples']):<6}                    │
└──────────────────────────────────────────┘
 
SPRACHEN
{lang_lines}
 
THEMEN
{topic_lines}
 
──────────────────────────────────────────
{fehler_block}
{scope_block}
══════════════════════════════════════════
🔗 {github_url}
"""


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    print(f"📊 Analysiere Wiesel-Chats für {target} ...")
    result = analyse(target)

    # Write report
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"{target}.md"
    report_text = build_report(result)
    report_path.write_text(report_text, encoding="utf-8")
    print(f"✅ Report geschrieben: {report_path}")

    # Git push via gh CLI
    repo_root = Path(__file__).parent.parent
    subprocess.run(["git", "add", f"reports/{target}.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", f"report: {target}"], cwd=repo_root, check=True)
    subprocess.run(["git", "push"], cwd=repo_root, check=True)
    print(f"✅ Report gepusht: reports/{target}.md")

    # Print summary
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Send email
    send_email(
        subject=f"[Wiesel] Tagesbericht {target}",
        body=email_summary(result),
    )
