from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "knowledge_base"


def test_starthilfe_sources_are_imported_once_with_substantive_guidance():
    expected = {
        "studienstart/starthilfe-fau-ws2627.md": "https://www.fau.de/studium/studienorganisation/studienstart/faqs-semesterbeginn/",
        "studienstart/einstiegstag-2026.md": "https://www.fau.de/studium/studienorganisation/studienstart/vorkurse-und-einfuehrungsveranstaltungen/",
        "studienorganisation/studienangebot-bachelor-wiso.md": "https://www.wiso.rw.fau.de/studium/studienangebot/bachelor/",
        "studienorganisation/studienfinanzierung-ueberblick.md": "https://www.fau.de/studium/studienorganisation/studienfinanzierung/",
        "uni-leben/wohnen.md": "https://www.fau.de/studium/studentisches-leben/wohnen/",
        "uni-leben/vernetzen-kultur-freizeit.md": "https://www.fau.de/studium/studentisches-leben/vernetzen-und-engagieren/",
    }

    for relative_path, source_url in expected.items():
        content = (KB / relative_path).read_text(encoding="utf-8")
        assert content.count(source_url) == 1
        assert "Gecrawlt am: 2026-09-21" in content
        assert len(content) > 700


def test_starthilfe_refresh_references_existing_deep_dives_instead_of_copying_them():
    starthilfe = (KB / "studienstart/starthilfe-fau-ws2627.md").read_text(encoding="utf-8")
    finanzierung = (KB / "studienorganisation/studienfinanzierung-ueberblick.md").read_text(encoding="utf-8")
    wohnen = (KB / "uni-leben/wohnen.md").read_text(encoding="utf-8")
    kultur = (KB / "uni-leben/vernetzen-kultur-freizeit.md").read_text(encoding="utf-8")

    assert "plattformen/campo.md" in starthilfe
    assert "plattformen/studon.md" in starthilfe
    assert "uni-leben/bafoeg.md" in finanzierung
    assert "uni-leben/stipendien.md" in finanzierung
    assert "anlaufstellen/studierendenwerk.md" in wohnen
    assert "uni-leben/hochschulsport.md" in kultur


if __name__ == "__main__":
    test_starthilfe_sources_are_imported_once_with_substantive_guidance()
    test_starthilfe_refresh_references_existing_deep_dives_instead_of_copying_them()
    print("knowledge-base starthilfe tests passed")
