from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "knowledge_base" / "studienorganisation" / "abkuerzungen-wiso.md"
SYSTEM_PROMPT = ROOT / "system-prompt.md"


def test_explains_common_wiwi_shortcuts_with_full_names_and_source():
    assert GLOSSARY.exists()

    content = GLOSSARY.read_text(encoding="utf-8")

    assert "**UuU**" in content
    assert "Unternehmer und Unternehmen" in content
    assert "**UMV**" in content
    assert "Unternehmen, Märkte, Volkswirtschaften" in content
    assert "**RSZ**" in content
    assert "Regelstudienzeit" in content
    assert "MHB_WiWi_PO_20252_ab-WS-2025-26_V2.pdf" in content


def test_prompt_expands_known_study_shortcuts_before_asking_for_clarification():
    prompt = SYSTEM_PROMPT.read_text(encoding="utf-8")

    assert "Studienkürzel" in prompt
    assert "anhand der Wissensbasis auf" in prompt
    assert "frage ich nach dem Kontext" in prompt
