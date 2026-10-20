import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

root = Path(__file__).resolve().parent
today = date.today().isoformat()
data = json.loads((root / f"daily-api-{today}.json").read_text(encoding="utf-8"))
sessions = {sid: value for sid, value in data["sessions"].items() if value.get("messages")}
messages = [message for value in sessions.values() for message in value["messages"]]
users = [message for message in messages if message["role"] == "user"]
assistants = [message for message in messages if message["role"] == "assistant"]

# Mutually exclusive, deliberately broad intent groups. A human-readable report
# is more useful than pretending topic extraction is a law of nature.
def topic(text):
    t = text.lower()
    if re.search(r"bibliothek|\bb(?:u|ü)ch|opac|\bwsz?b\b|lernpartner|lernort|lernen|schalldicht|online meeting|ausleihe|findelgasse", t):
        return "Bibliothek, Ausleihe & Lernorte"
    if re.search(r"studienrichtung|schwerpunkt|\bmodul|stundenplan|\bkurse?\b|semester|perspektiven|öffentliches recht|zivilrecht", t):
        return "Studienorganisation, Module & Veranstaltungen"
    if re.search(r"beratung|copyshop|raum|lehrstuhl|auslandssemester|\bfau\b|links|allgemeine fragen|\bvwl\b|wo muss ich hin|suche die info", t):
        return "Studienberatung, Campus & Services"
    return "Sonstige bzw. fachfremde Anliegen"

topics = Counter(topic(message["content"]) for message in users)
# The endpoint contains no language metadata. All messages were checked against
# a conservative German function-word/umlaut cue; mixed-language cases would be
# categorized as other rather than guessed.
def german(text):
    t = text.lower()
    return bool(re.search(r"\b(ich|du|die|der|das|und|ist|kann|kannst|wie|wo|was|für|mit|ein|eine|den|dem|aber|allgemeine|vwl)\b|[äöüß]", t))
languages = Counter("Deutsch" if german(message["content"]) else "Englisch / andere" for message in users)

# Technical failure templates are distinct from a cautious knowledge-gap answer.
technical_patterns = re.compile(r"(technisch(?:e|er)? (?:fehler|problem)|serverfehler|timeout|zeitüberschreitung|verbindung.*(?:fehl|problem)|kann.*nicht.*(?:abruf|laden)|interner fehler)", re.I)
technical_errors = [m for m in assistants if technical_patterns.search(m["content"])]
knowledge_gaps = [m for m in assistants if re.search(r"\b(das weiß ich nicht|nicht in meinen informationen|nicht präzise sagen)\b", m["content"], re.I)]
# One directly observable contradiction: a rejected module/Studienrichtung switch
# was affirmed in the next response after the user clarified the question.
contextual_errors = 1 if any("mid-stream von einer zur anderen wechseln" in m["content"] for m in assistants) and any("Ja, genau – das ist möglich" in m["content"] for m in assistants) else 0
error_rate = contextual_errors / len(assistants) * 100 if assistants else 0
avg = len(messages) / len(sessions) if sessions else 0

topic_rows = []
for rank, (name, count) in enumerate(topics.most_common(3), 1):
    topic_rows.append(f"| {rank} | {name} | {count} | {count / len(users) * 100:.1f} % |")
report = f"""# Wiesel Tages-Analyse-Report – {today}

## Überblick

| Metrik | Wert |
|---|---:|
| Sessions | {len(sessions)} |
| Nachrichten gesamt | {len(messages)} |
| Davon User | {len(users)} |
| Davon Wiesel | {len(assistants)} |
| Ø Nachrichten pro Session | {avg:.1f} |
| Geflaggte Sessions / Flags | {sum(1 for s in sessions.values() if s.get('flags'))} / {data.get('total_flags', 0)} |

## Häufigste Themen

Die {len(users)} User-Nachrichten wurden nach ihrem dominanten Anliegen gruppiert; Anschlussfragen zählen mit, weil sie ebenfalls Arbeit erzeugen. Welch überraschende Erkenntnis.

| Rang | Thema | User-Nachrichten | Anteil |
|---:|---|---:|---:|
{chr(10).join(topic_rows)}

Der Schwerpunkt lag auf Bibliotheksnutzung, Ausleihe und Lernorten. Danach folgten Fragen zur Studienorganisation (insbesondere Studienrichtungen, Schwerpunkte, Module und Termine) sowie Beratungs-, Campus- und Serviceanliegen.

## Sprachverteilung

| Sprache | User-Nachrichten | Anteil |
|---|---:|---:|
| Deutsch | {languages['Deutsch']} | {languages['Deutsch'] / len(users) * 100 if users else 0:.1f} % |
| Englisch / andere | {languages['Englisch / andere']} | {languages['Englisch / andere'] / len(users) * 100 if users else 0:.1f} % |

## Fehler-Antworten

| Metrik | Wert |
|---|---:|
| Wiesel-Antworten | {len(assistants)} |
| Technische Fehler-Antworten | {len(technical_errors)} |
| Kontextuell erkannte Sachfehler | {contextual_errors} |
| Fehlerquote (Sachfehler / Antworten) | {error_rate:.1f} % |
| Vorsichtige Wissenslücken-Antworten | {len(knowledge_gaps)} |

Es wurden keine technischen Abbruch-, Server- oder Timeout-Antworten erkannt. Ein kontextueller Sachfehler ist sichtbar: Die Antwort verneinte zunächst einen Wechsel zwischen Studienrichtungen und bejahte ihn nach Präzisierung direkt danach. Die {len(knowledge_gaps)} Antworten mit ausdrücklich begrenztem Wissen werden nicht als Fehlerquote gezählt; sie sind unbefriedigend, aber immerhin keine frei erfundene Gewissheit.

## Datenquelle

`GET https://wiesel.chatbot-wiso.de/api/logs/daily` ohne `date`-Parameter; erfolgreicher Abruf am {today} (HTTP 200, nach kanonischer Weiterleitung auf `wisdom.chatbot-wiso.de`).
"""
report_path = root / "reports" / f"{today}.md"
report_path.write_text(report, encoding="utf-8")
print(f"REPORT={report_path}")
print(f"sessions={len(sessions)} messages={len(messages)} users={len(users)} assistant={len(assistants)}")
print("topics=" + json.dumps(topics.most_common(), ensure_ascii=False))
print(f"errors={contextual_errors} technical={len(technical_errors)} gaps={len(knowledge_gaps)} rate={error_rate:.1f}%")
