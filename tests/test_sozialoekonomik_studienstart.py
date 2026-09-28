from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "backend" / "main.py"
SOZOEKO_FAQ = ROOT / "knowledge_base" / "studienstart" / "sozialoekonomik-ba-faq.md"


def test_studienstart_prompt_requires_subject_before_general_checklist():
    source = MAIN.read_text(encoding="utf-8")

    assert "Bei Fragen zum Studienstart oder zu Einführungsveranstaltungen" in source
    assert "frage zuerst nach dem Studiengang" in source
    assert "keine allgemeine Checkliste" in source
    assert "Sozialökonomik" in source


def test_sozialoekonomik_faq_prevents_wrong_confirmation_and_registration_advice():
    content = SOZOEKO_FAQ.read_text(encoding="utf-8")

    expected_facts = [
        "Es gibt keine Anmeldebestätigung.",
        "Nach dem Anmeldeschluss am 05.10.2026",
        "bis Donnerstag vor dem Planspiel (08.10.2026) keine E-Mail erhalten",
        "Anmeldung verpasst? Kontaktiere wiso-ba-sozoek@fau.de",
        "Nur der Informationstag am Dienstag ist optional",
        "Mittwoch und Donnerstag sind verpflichtend",
    ]
    for fact in expected_facts:
        assert fact in content
