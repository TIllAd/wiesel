from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = ROOT / "knowledge_base" / "studienstart" / "einfuehrungsveranstaltungen.md"


def test_einfuehrungsveranstaltungen_cover_official_child_pages_once():
    content = OVERVIEW.read_text(encoding="utf-8")

    expected_urls = [
        "https://www.wiso.rw.fau.de/studium/studienbeginn/einfuehrungsveranstaltungen/erstsemesterbegruessung/",
        "https://www.wiso.rw.fau.de/studium/studienorganisation/studienstart/einfuehrungsveranstaltungen/perspektiven-der-wirtschaftswissenschaften/",
        "https://www.wiso.rw.fau.de/studium/studienbeginn/einfuehrungsveranstaltungen/planspiel-sozialoekonomik/",
        "https://www.wiso.rw.fau.de/studium/studienbeginn/einfuehrungsveranstaltungen/win-projektwoche/",
        "https://www.wiso.rw.fau.de/studium/studienbeginn/einfuehrungsveranstaltungen/bachelor-ibs-und-ies/",
    ]

    assert "Gecrawlt am: 2026-09-04" in content
    for url in expected_urls:
        assert content.count(url) == 1


def test_einfuehrungsveranstaltungen_point_to_existing_deep_dive_articles():
    content = OVERVIEW.read_text(encoding="utf-8")

    assert "planspiel/einfuehrungsveranstaltung.md" in content
    assert "studienstart/sozialoekonomik-ba-faq.md" in content
    assert "studienstart/erstsemesterbegruessung-zeitplan-ws2627.md" in content
