from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.evidence_guard import apply_evidence_guard


KB = """
# Prüfungsamt WiSo
Ansprechpartner für Prüfungsanmeldung, Krankmeldung, Fristen und Formulare.
Website: https://www.fau.de/studium/studienorganisation/pruefungen/pruefungsamt-rw/wirtschafts-und-sozialwissenschaften/

# Fachstudienberatung WiSo
Quelle: https://www.wiso.rw.fau.de/studium/im-studium/fachstudienberatung/
"""


def test_belegpflichtige_antwort_ohne_quelle_wird_sicher_weitergeleitet():
    reply = "Normale Prüfungen darfst du viermal wiederholen."

    guarded = apply_evidence_guard(
        "Wie oft darf ich eine Prüfung wiederholen?", reply, KB
    )

    assert guarded != reply
    assert "viermal" not in guarded
    assert "Prüfungsamt" in guarded
    assert "https://www.fau.de/studium/studienorganisation/pruefungen/pruefungsamt-rw/wirtschafts-und-sozialwissenschaften/" in guarded


def test_belegpflichtige_antwort_mit_kb_quelle_erhaelt_sichtbaren_quellenhinweis():
    reply = "Die Regel steht beim [Prüfungsamt](https://www.fau.de/studium/studienorganisation/pruefungen/pruefungsamt-rw/wirtschafts-und-sozialwissenschaften/)."

    guarded = apply_evidence_guard(
        "Bis wann kann ich mich von einer Prüfung abmelden?", reply, KB
    )

    assert guarded.startswith(reply)
    assert "Quelle:" in guarded


def test_unverbindliche_orientierungsantwort_bleibt_unveraendert():
    reply = "Campo ist für die Studienverwaltung, StudOn für Kursmaterialien."

    assert apply_evidence_guard("Was ist der Unterschied zwischen Campo und StudOn?", reply, KB) == reply


def test_studienberatung_ohne_sichtbaren_link_wird_nicht_durch_pruefungsregel_ersetzt():
    reply = "Die Zentrale Studienberatung WiSo hilft bei allgemeinen Fragen zum Studium."

    assert apply_evidence_guard("Wo ist die Studienberatung?", reply, KB) == reply


def test_vorlesungsabmeldung_ohne_pruefungsbezug_wird_nicht_durch_pruefungsamt_ersetzt():
    reply = "Ob du dich abmelden kannst, hängt von der jeweiligen Veranstaltung ab."

    assert apply_evidence_guard("Kann ich mich von einer Vorlesung abmelden?", reply, KB) == reply


def test_fau_mailadresse_ohne_sichtbaren_link_wird_nicht_durch_pruefungsamt_ersetzt():
    reply = "Deine FAU-Mailadresse findest du in den offiziellen IT-Konten-Einstellungen."

    assert apply_evidence_guard("Wie ist meine FAU-Mailadresse aufgebaut?", reply, KB) == reply


def test_chat_pipeline_runs_the_evidence_gate_with_the_loaded_knowledge_base():
    main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")

    assert "from backend.evidence_guard import apply_evidence_guard" in main
    assert "text = apply_evidence_guard(query, text, kb_content)" in main


def test_system_prompt_requires_an_explicit_source_for_binding_information():
    prompt = (ROOT / "system-prompt.md").read_text(encoding="utf-8")

    assert "Belegpflicht für verbindliche Angaben" in prompt
    assert "sichtbaren Quellenhinweis" in prompt
    assert "Keine passende Fundstelle = keine konkrete Regel" in prompt
