from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PROMPT = ROOT / "system-prompt.md"


def test_prompt_expands_known_study_shortcuts_before_asking_for_clarification():
    prompt = SYSTEM_PROMPT.read_text(encoding="utf-8")

    assert "Studienkürzel" in prompt
    assert "anhand der Wissensbasis auf" in prompt
    assert "frage ich nach dem Kontext" in prompt
