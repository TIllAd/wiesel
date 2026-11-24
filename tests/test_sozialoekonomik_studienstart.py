from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "backend" / "main.py"


def test_studienstart_prompt_requires_subject_before_general_checklist():
    source = MAIN.read_text(encoding="utf-8")

    assert "Bei Fragen zum Studienstart oder zu Einführungsveranstaltungen" in source
    assert "frage zuerst nach dem Studiengang" in source
    assert "keine allgemeine Checkliste" in source
    assert "Sozialökonomik" in source
