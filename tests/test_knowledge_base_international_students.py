from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISS_REFERENCE = ROOT / "knowledge_base" / "anlaufstellen" / "international-student-servicepoint.md"
ISS_URL = (
    "https://www.studon.fau.de/studon/ilias.php?baseClass=ilrepositorygui&"
    "cmdNode=13a:qe&cmdClass=ilObjCategoryGUI&ref_id=6292770"
)


def test_international_student_servicepoint_reference_is_available_with_official_studon_link():
    content = ISS_REFERENCE.read_text(encoding="utf-8")

    assert "# FAU International Student Servicepoint (ISS)" in content
    assert ISS_URL in content
    assert "internationale Studierende" in content
    assert "StudOn-Anmeldung" in content
