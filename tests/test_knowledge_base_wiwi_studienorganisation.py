from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "knowledge_base"
COURSE_PLANNING = KB / "studienorganisation" / "kursanmeldung-und-stundenplan-wiwi.md"
MODULE_GUIDE = KB / "studienorganisation" / "modulhandbuch-pdf.md"
INTRODUCTION = KB / "studienstart" / "einfuehrungsveranstaltungen.md"
INTERNAL_KB_VIEW = ROOT / "backend" / "static" / "docs" / "internal" / "knowledge-base.html"


def test_wiwi_course_registration_and_timetable_article_covers_both_platforms():
    content = COURSE_PLANNING.read_text(encoding="utf-8")

    for expected in [
        "StudOn",
        "Campo",
        "Modulname oder der Modulnummer",
        "Studienplaner mit Modulplan",
        "Übung, Tutorium oder andere Zusatzangebote",
        "Magazin → Meine Kurse",
        "automatisch in Campo übertragen",
    ]:
        assert expected in content


def test_wiwi_course_registration_and_timetable_article_is_editable_in_the_internal_kb_view():
    content = INTERNAL_KB_VIEW.read_text(encoding="utf-8")

    assert "kursanmeldung-und-stundenplan-wiwi.md" in content


def test_module_guide_explains_the_study_plan_module_number_and_workload():
    content = MODULE_GUIDE.read_text(encoding="utf-8")

    for expected in [
        "Studienverlaufsplan",
        "Modulnummer",
        "StudOn oder Campo",
        "1 ECTS-Punkt entspricht 30 Stunden Arbeitsaufwand",
        "aufbauen",
    ]:
        assert expected in content


def test_wiwi_introduction_explains_where_to_find_the_digital_rallye_and_its_consequence():
    content = INTRODUCTION.read_text(encoding="utf-8")

    for expected in [
        "Reiter „Prüfungsleistung“",
        "gewählten StudOn-Durchgang",
        "fehlerhafte oder fehlende Eingaben",
        "negativ auf die Prüfungsleistung auswirken",
    ]:
        assert expected in content
