from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "knowledge_base" / "anlaufstellen" / "ansprechpersonen-wiso.md"
DIRECTORY_SCRAPER = ROOT / "backend" / "scraper" / "ansprechpersonen_scraper.py"
PLACES = ROOT / "knowledge_base" / "orte_navigation.md"
MENSA_CRAWLER = ROOT / "backend" / "mensa_crawler.py"


def test_mensa_insel_schuett_uses_verified_address_everywhere():
    expected = "Andreij-Sacharow-Platz 1, 90403 Nürnberg"

    assert expected in PLACES.read_text(encoding="utf-8")
    assert expected in MENSA_CRAWLER.read_text(encoding="utf-8")


def test_ansprechpersonen_directory_has_study_routing_and_official_sources():
    content = DIRECTORY.read_text(encoding="utf-8")

    assert "# Anlaufstellen & Ansprechpersonen an der FAU WiSo" in content
    assert "Zentrale Studienberatung" in content
    assert "Fachstudienberatung" in content
    assert "Nikhila Raghavan" in content
    assert "PD Dr. Andreas Damelang" in content
    assert "wiso-ba-win@fau.de" in content
    assert "Büro für Internationale Beziehungen" in content
    assert "Career Service" in content
    assert "https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenberatung/fachstudienberatung/" in content


def test_diversity_reference_uses_wiso_homepage_not_removed_detail_page():
    obsolete = "https://www.wiso.rw.fau.de/fachbereich/strategie/handlungsfeld-people/diversitaet-am-fachbereich/"
    expected = "Diversity-Angebote WiSo und Mentoring/Support. Quelle: https://www.wiso.rw.fau.de/"

    for path in (DIRECTORY, DIRECTORY_SCRAPER):
        content = path.read_text(encoding="utf-8")
        assert expected in content
        assert obsolete not in content


def test_ansprechpersonen_directory_covers_professors_and_team_contacts():
    content = DIRECTORY.read_text(encoding="utf-8")

    assert content.count("https://www.wiso.rw.fau.de/forschung/forschungsprofil/professorenschaft/prof-") >= 50
    for person in ["Ulrike Marx", "Beatrix Hillen", "Angela Brunner", "Monika Hanisch", "Julia Neukam"]:
        assert person in content
    assert "Prof. Dr. Gatzert (†)" in content
    assert "nicht als aktuelle ansprechpartnerin" in content.lower()
    assert "Prof. Dr. Martin Abraham" in content
    assert "Prof. Dr. Michael Amberg" in content
