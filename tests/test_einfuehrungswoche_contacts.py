from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = ROOT / "knowledge_base" / "planspiel" / "ablauf-einfuehrungswoche.md"


def test_einfuehrungswoche_lists_the_mentor_contact():
    knowledge = SCHEDULE.read_text(encoding="utf-8")

    assert "wiso-mentoren@fau.de" in knowledge
    assert "zur Einführungswoche, zum Planspiel sowie zu Coaching und Mentoring" in knowledge


def test_planspiel_schedule_states_that_mentors_help_create_the_timetable():
    knowledge = SCHEDULE.read_text(encoding="utf-8")

    assert "gemeinsame Stundenplanerstellung mit Mentorinnen und Mentoren" in knowledge
