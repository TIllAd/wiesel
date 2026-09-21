from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = ROOT / "knowledge_base" / "studienstart" / "einfuehrungsveranstaltungen.md"
CATEGORIES = ROOT / "knowledge_base" / "categories.json"


def test_category_g_is_named_for_all_wiso_introduction_events():
    categories = CATEGORIES.read_text(encoding="utf-8")

    assert '"code": "E"' in categories
    assert '"name": "Anlaufstellen & Ansprechpersonen"' in categories
    assert '"code": "G"' in categories
    assert '"name": "Einführungsveranstaltungen an der WiSo"' in categories
    assert "BizzTrainer" not in categories


def test_einfuehrungsveranstaltungen_record_current_program_specific_details():
    content = OVERVIEW.read_text(encoding="utf-8")

    for expected in [
        "Mark Weilbach",
        "08.10.2026",
        "Luisa Wieser",
        "Laura Pohl",
        "René Gröbner",
        "34651",
        "14. bis 16.10.2026",
        "28.09.2026 bis 11.10.2026",
        "06. bis 09.10.2026",
        "12.10.2026",
    ]:
        assert expected in content


def test_einfuehrungsveranstaltungen_cover_official_child_pages_once():
    content = OVERVIEW.read_text(encoding="utf-8")

    expected_urls = [
        "https://www.wiso.rw.fau.de/studium/studienorganisation/studienstart/erstsemesterbegruessung/",
        "https://www.professur-wirtschaftspaedagogik.rw.fau.de/en/einfuhrung-perspektiven-der-wirtschaftswissenschaften/",
        "https://www.wiso.rw.fau.de/studium/studienorganisation/studienstart/einfuehrungsveranstaltungen/planspiel-sozialoekonomik/",
        "https://www.it-management.rw.fau.de/lehre/bachelor/win-projektwoche/",
        "https://www.international-business-economics.wiso.rw.fau.eu",
    ]

    assert "Stand: 2026-09-21" in content
    for url in expected_urls:
        assert content.count(url) == 1


def test_einfuehrungsveranstaltungen_point_to_existing_deep_dive_articles():
    content = OVERVIEW.read_text(encoding="utf-8")

    assert "planspiel/einfuehrungsveranstaltung.md" in content
    assert "studienstart/sozialoekonomik-ba-faq.md" in content
    assert "studienstart/erstsemesterbegruessung-zeitplan-ws2627.md" in content
