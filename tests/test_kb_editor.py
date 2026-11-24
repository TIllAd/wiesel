"""Wissensbasis-Editor und Struktur der Wissensbasis.

Ersetzt die früheren Inhalts-Tests: geprüft wird die Mechanik (Speichern,
Versionen, Rückgängig, Auto-Dateien, Prüfungen) und dass jede Datei sauber
aufgebaut ist – nicht, welche Fakten drinstehen. Inhalte prüft das Team über
die Standardfragen im Editor.
"""

import asyncio
import importlib
import os
import shutil
import sys
import time
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import kb_store  # noqa: E402
from backend.jobs import source_watch  # noqa: E402


# ── Struktur der echten Wissensbasis ─────────────────────────────────────────

def _real_files():
    base = ROOT / "knowledge_base"
    return base, [p for p in kb_store.md_files(base) if not kb_store.is_auto(kb_store.rel(base, p))]


def test_every_knowledge_file_is_well_formed():
    base, files = _real_files()
    assert len(files) > 20
    problems = []
    for path in files:
        meta, body = kb_store.parse(path.read_text(encoding="utf-8"))
        errors = [i["text"] for i in kb_store.check(meta, body) if i["level"] == "fehler"]
        if errors:
            problems.append(f"{kb_store.rel(base, path)}: {errors}")
        if not any(line.startswith("# ") for line in body.splitlines()):
            problems.append(f"{kb_store.rel(base, path)}: keine Überschrift")
    assert not problems, "\n".join(problems)


def test_editor_header_never_reaches_the_model():
    base, _ = _real_files()
    content, _ = kb_store.prompt_content(base)
    assert "pruefen_bis:" not in content
    assert "verantwortlich:" not in content


# ── kb_store ─────────────────────────────────────────────────────────────────

def test_frontmatter_roundtrip_and_status():
    text = kb_store.compose({"verantwortlich": "Studienbüro", "pruefen_bis": "2027-03-31"}, "# Titel\nInhalt\n")
    meta, body = kb_store.parse(text)
    assert meta == {"verantwortlich": "Studienbüro", "pruefen_bis": "2027-03-31"}
    assert body.startswith("# Titel")
    today = date(2027, 3, 1)
    assert kb_store.review_status(meta, today) == "bald"
    assert kb_store.review_status({"pruefen_bis": "2027-01-01"}, today) == "abgelaufen"
    assert kb_store.review_status({"pruefen_bis": "2028-01-01"}, today) == "ok"
    assert kb_store.review_status({}, today) == "kein-datum"
    assert kb_store.review_status({"pruefen_bis": "morgen"}, today) == "ungueltig"


def test_checks_flag_placeholders_but_not_normal_links():
    issues = kb_store.check({"pruefen_bis": "2099-01-01", "verantwortlich": "x"},
                           "# T\nQuelle: https://a.de\n[Link](https://b.de) und [LINK ZUR WISDOM-SEITE]\n")
    texts = " ".join(i["text"] for i in issues)
    assert "[LINK ZUR WISDOM-SEITE]" in texts
    assert "[Link]" not in texts
    assert [i for i in kb_store.check({}, "kurz") if i["level"] == "fehler"]
    assert [i for i in kb_store.check({"pruefen_bis": "31.13.2027"}, "# T\n" + "x" * 40) if i["level"] == "fehler"]


def test_source_url_variants():
    assert kb_store.source_url("Quelle: https://a.de/x.") == "https://a.de/x"
    assert kb_store.source_url("**Quelle:** https://b.de") == "https://b.de"
    assert kb_store.source_url("Website: https://c.de") == "https://c.de"
    assert kb_store.source_url("kein Link") is None


def test_safe_path_rejects_escapes(tmp_path):
    for bad in ["../system-prompt.md", "a/../../x.md", ".quellen-status.json", "x.txt", "_intern/a.md", ".git/x.md"]:
        with pytest.raises(ValueError):
            kb_store.safe_path(tmp_path, bad)
    assert kb_store.safe_path(tmp_path, "ordner/datei.md").name == "datei.md"


def test_stale_auto_files_are_not_given_to_the_model(tmp_path):
    (tmp_path / "mensa-woche.md").write_text("# Mensa\nAlter Plan", encoding="utf-8")
    (tmp_path / "thema.md").write_text("---\npruefen_bis: 2000-01-01\n---\n# Thema\nBleibt drin", encoding="utf-8")
    old = time.time() - 3 * 24 * 3600
    os.utime(tmp_path / "mensa-woche.md", (old, old))
    content, skipped = kb_store.prompt_content(tmp_path)
    assert skipped == ["mensa-woche.md"]
    assert "Alter Plan" not in content
    assert "Bleibt drin" in content  # überfällige Dateien bleiben aktiv, nur markiert
    os.utime(tmp_path / "mensa-woche.md", None)
    content, skipped = kb_store.prompt_content(tmp_path)
    assert "Alter Plan" in content and not skipped


def test_slugify():
    assert kb_store.slugify("Urlaubssemester & Beurlaubung") == "urlaubssemester-beurlaubung"
    assert kb_store.slugify("Prüfungsämter Übersicht") == "pruefungsaemter-uebersicht"


# ── Quellen-Wächter ──────────────────────────────────────────────────────────

def test_source_watch_flags_changes_and_never_touches_files(tmp_path):
    f = tmp_path / "a.md"
    original = "# A\nQuelle: https://example.org/a\nText\n"
    f.write_text(original, encoding="utf-8")
    pages = {"v": "<html><body><main><p>Version 1</p></main></body></html>"}
    fetch = lambda url: pages["v"]  # noqa: E731
    state = source_watch.run(tmp_path, fetcher=fetch, pause=0)
    assert state["a.md"]["geaendert_seit"] is None
    pages["v"] = "<html><body><nav>Menü neu</nav><main><p>Version 1</p></main></body></html>"
    assert source_watch.run(tmp_path, fetcher=fetch, pause=0)["a.md"]["geaendert_seit"] is None  # Menü egal
    pages["v"] = "<html><body><main><p>Version 2</p></main></body></html>"
    assert source_watch.run(tmp_path, fetcher=fetch, pause=0)["a.md"]["geaendert_seit"]
    source_watch.mark_reviewed(tmp_path, "a.md", "test@fau.de")
    assert source_watch.load_state(tmp_path)["a.md"]["geaendert_seit"] is None
    assert source_watch.run(tmp_path, fetcher=fetch, pause=0)["a.md"]["geaendert_seit"] is None
    assert f.read_text(encoding="utf-8") == original


# ── API-Ablauf ───────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    shutil.copytree(ROOT / "knowledge_base", kb)
    monkeypatch.setenv("WISDOM_KB_DIR", str(kb))
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    for name in [m for m in sys.modules if m.startswith("backend.main") or m == "backend.routers.kb_editor"]:
        del sys.modules[name]
    main = importlib.import_module("backend.main")
    from fastapi.testclient import TestClient

    async def fake_ask(question, overrides=None):
        kb_text = main.load_knowledge_base(overrides)
        return f"Antwort ENTWURF={'ENTWURFTEXT' in kb_text}"

    main.kb_editor_router._ask = fake_ask
    c = TestClient(main.app)
    c.headers.update({"x-admin-key": "test-admin"})
    return c, main, kb


def test_editor_requires_login(client):
    c, _, _ = client
    from fastapi.testclient import TestClient
    anon = TestClient(c.app)
    assert anon.get("/api/kb/files").status_code == 401
    assert anon.put("/api/kb/file", json={"path": "a.md", "body": "x"}).status_code == 401


def test_save_is_live_versioned_and_undoable(client):
    c, main, _ = client
    path = "plattformen/campo.md"
    f = c.get("/api/kb/file", params={"path": path}).json()
    r = c.put("/api/kb/file", json={"path": path, "body": f["body"] + "\nENTWURFTEXT\n", "verantwortlich": "Studienbüro",
                                    "pruefen_bis": "2027-03-31", "base_mtime": f["base_mtime"], "kommentar": "Test"})
    assert r.status_code == 200 and r.json()["saved"]
    assert "ENTWURFTEXT" in main.load_knowledge_base()

    stale = c.put("/api/kb/file", json={"path": path, "body": f["body"], "base_mtime": f["base_mtime"]})
    assert stale.status_code == 409 and "geändert" in stale.json()["detail"]

    versions = c.get("/api/kb/history", params={"path": path}).json()["versions"]
    assert [v["action"] for v in versions] == ["geaendert", "ausgangsstand"]
    assert versions[0]["comment"] == "Test"
    assert c.post(f"/api/kb/restore/{versions[-1]['id']}").status_code == 200
    assert "ENTWURFTEXT" not in main.load_knowledge_base()


def test_rejects_empty_auto_and_outside_files(client):
    c, _, _ = client
    f = c.get("/api/kb/file", params={"path": "plattformen/campo.md"}).json()
    assert c.put("/api/kb/file", json={"path": "plattformen/campo.md", "body": "kurz", "base_mtime": f["base_mtime"]}).status_code == 422
    assert c.put("/api/kb/file", json={"path": "../system-prompt.md", "body": "x" * 50}).status_code == 400
    assert c.put("/api/kb/file", json={"path": "mensa-woche.md", "body": "x" * 50}).status_code == 400


def test_new_delete_and_restore(client):
    c, _, kb = client
    r = c.post("/api/kb/new", json={"title": "Urlaubssemester", "folder": "studienorganisation", "pruefen_bis": "2027-09-30"})
    assert r.status_code == 200
    path = r.json()["path"]
    assert c.post("/api/kb/new", json={"title": "Urlaubssemester", "folder": "studienorganisation"}).status_code == 409
    assert c.delete("/api/kb/file", params={"path": path}).status_code == 200
    assert not (kb / path).exists()
    deleted = c.get("/api/kb/deleted").json()["deleted"]
    assert deleted[0]["path"] == path
    assert c.post(f"/api/kb/restore/{deleted[0]['id']}").json()["restored"] == path
    assert (kb / path).exists()


def test_probe_with_draft_and_standard_questions(client):
    c, _, _ = client
    r = c.post("/api/kb/probe", json={"frage": "Was ist campo?", "path": "plattformen/campo.md", "body": "# Campo\nENTWURFTEXT"})
    assert r.json() == {"antwort": "Antwort ENTWURF=True", "mit_entwurf": True}
    assert c.post("/api/kb/probe", json={"frage": "Was ist campo?"}).json()["antwort"] == "Antwort ENTWURF=False"

    c.post("/api/kb/standardfragen", json={"frage": "Was ist campo?", "stichworte": "antwort, xyz | entwurf, fehlt"})
    result = c.post("/api/kb/standardfragen/run").json()["fragen"][0]
    assert result["letztes_ok"] is False
    assert result["fehlende"] == ["fehlt"]


def test_system_prompt_and_rules_are_editable_with_history(client):
    c, main, kb = client
    main.ensure_behavior_files()
    assert (kb / "_wisdom" / "system-prompt.md").is_file()
    files = {f["path"]: f for f in c.get("/api/kb/files").json()["files"]}
    assert files["_wisdom/system-prompt.md"]["behavior"] is True
    assert "_wisdom/regeln.md" in files

    # Regeln sind nicht Teil der Faktenbasis, aber Teil des Prompts.
    assert "Zusatzregeln" not in main.load_knowledge_base()
    f = c.get("/api/kb/file", params={"path": "_wisdom/regeln.md"}).json()
    r = c.put("/api/kb/file", json={"path": "_wisdom/regeln.md", "body": f["body"] + "\nREGEL-NEU: immer duzen.\n",
                                    "base_mtime": f["base_mtime"], "kommentar": "Test"})
    assert r.status_code == 200, r.text
    assert "REGEL-NEU" in main.build_system_prompt("KB")
    assert "REGEL-NEU" not in main.load_knowledge_base()

    # Entwurf des System-Prompts wirkt nur in der Probe, nicht live.
    sp = c.get("/api/kb/file", params={"path": "_wisdom/system-prompt.md"}).json()
    draft = {"_wisdom/system-prompt.md": sp["body"] + "\nENTWURF-PROMPT"}
    assert "ENTWURF-PROMPT" in main.build_system_prompt("KB", draft)
    assert "ENTWURF-PROMPT" not in main.build_system_prompt("KB")

    # Zu kurz = blockiert, Löschen = verboten, Verlauf = vorhanden.
    assert c.put("/api/kb/file", json={"path": "_wisdom/system-prompt.md", "body": "# Kurz\nnur ein Satz.",
                                       "base_mtime": sp["base_mtime"]}).status_code == 422
    assert c.delete("/api/kb/file", params={"path": "_wisdom/system-prompt.md"}).status_code == 400
    assert c.get("/api/kb/history", params={"path": "_wisdom/regeln.md"}).json()["versions"][0]["action"] == "geaendert"


def test_source_watch_ignores_network_errors_but_flags_dead_pages(tmp_path):
    import requests
    (tmp_path / "a.md").write_text("# A\nQuelle: https://www.fau.de/a\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\nQuelle: https://www.fau.de/b\n", encoding="utf-8")
    (tmp_path / "c.md").write_text("# C\nQuelle: https://example.org/weg\n", encoding="utf-8")
    calls = []

    def fetch(url):
        calls.append(url)
        if "fau.de" in url:
            raise requests.ConnectionError("Network is unreachable")
        response = requests.Response()
        response.status_code = 404
        raise requests.HTTPError(response=response)

    state = source_watch.run(tmp_path, fetcher=fetch, pause=0)
    assert state["a.md"].get("nicht_pruefbar") and not state["a.md"].get("fehler")
    assert state["b.md"].get("nicht_pruefbar")
    assert calls.count("https://www.fau.de/b") == 0  # Server nach erstem Timeout übersprungen
    assert state["c.md"]["fehler"] == "HTTP 404"


def test_database_is_mounted_as_folder_not_single_file():
    """Regression 24.11.2026: Einzeldatei-Mount + WAL = Datenverlust bei jedem Neustart."""
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "wiesel.db:/app/wiesel.db" not in compose
    assert "DATABASE_URL=sqlite:////app/backend/wiesel.db" in compose
    assert "./backend:/app/backend" in compose
