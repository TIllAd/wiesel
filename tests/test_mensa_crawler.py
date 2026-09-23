import importlib.util
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRAWLER_PATH = ROOT / "backend" / "mensa_crawler.py"

spec = importlib.util.spec_from_file_location("mensa_crawler", CRAWLER_PATH)
mensa_crawler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mensa_crawler)


def test_generate_markdown_marks_mensa_closed_when_no_menu_exists_today(monkeypatch):
    monkeypatch.setattr(mensa_crawler, "date", type("FixedDate", (), {
        "today": staticmethod(lambda: date(2026, 9, 23)),
        "fromisoformat": staticmethod(date.fromisoformat),
    }))
    data = {
        "insel_schuett": {
            "name": "Mensa Insel Schütt",
            "address": "Andreij-Sacharow-Platz 1, 90403 Nürnberg",
            "days": [{"date": "2026-09-28", "weekday": "Monday", "meals": [{"name": "Pasta", "category": "Essen 1", "allergens": [], "price_student": "3.00", "price_employee": None, "price_guest": None}]}],
        }
    }

    markdown = mensa_crawler.generate_markdown(data)

    assert "Mensa Insel Schütt: heute geschlossen (kein Speiseplan veröffentlicht)." in markdown


def test_navigation_kb_does_not_present_regular_cafeteria_hours_as_live_status():
    content = (ROOT / "knowledge_base" / "orte_navigation.md").read_text(encoding="utf-8")

    assert "Reguläre Öffnungszeiten, nicht tagesaktuell" in content
    assert "Nicht aus den regulären Zeiten ableiten, ob heute geöffnet ist." in content


def test_lange_gasse_closure_parser_recognizes_semester_break_notice():
    notice = "Liebe Gäste, in den Semesterferien haben wir wie folgt geöffnet/geschlossen: 22.08. bis 04.10.: Geschlossen"

    closure = mensa_crawler.parse_closure_notice(notice, date(2026, 9, 23))

    assert closure == "22.08. bis 04.10."


def test_generate_markdown_does_not_duplicate_special_status_as_missing_menu(monkeypatch):
    monkeypatch.setattr(mensa_crawler, "date", type("FixedDate", (), {
        "today": staticmethod(lambda: date(2026, 9, 23)),
        "fromisoformat": staticmethod(date.fromisoformat),
    }))
    data = {"lange_gasse": {
        "name": "Cafeteria Lange Gasse",
        "address": "Lange Gasse 20, 90403 Nürnberg",
        "days": [],
        "current_status": "heute geschlossen (veröffentlichte Sonderöffnungszeit: 22.08. bis 04.10.)",
    }}

    markdown = mensa_crawler.generate_markdown(data)

    assert markdown.count("Cafeteria Lange Gasse") == 1
