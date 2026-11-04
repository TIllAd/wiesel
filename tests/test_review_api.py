"""Unit tests for the file-backed chat-review API helpers."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "backend" / "review_api.py"


def load_module():
    spec = importlib.util.spec_from_file_location("review_api_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ReviewApiTests(unittest.TestCase):
    def test_load_evaluations_filters_ok_records_since_and_exposes_last_message_date(self):
        review_api = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evaluations = root / "evaluations"
            evaluations.mkdir()
            (evaluations / "2026-11-03.jsonl").write_text(
                "\n".join([
                    json.dumps({"session_id": "old", "reviewed_at": "2026-11-03 09:00:00", "status": "ok", "bewertung": {"kategorie": "wissensluecke", "schwere": 2, "thema": "Frist", "begruendung": "Unklar.", "kb_vorschlag": "Ergänzen.", "auszug": ["Zitat"]}}),
                    json.dumps({"session_id": "failed", "reviewed_at": "2026-11-03 09:01:00", "status": "error"}),
                ]) + "\n",
                encoding="utf-8",
            )
            (evaluations / "2026-11-04.jsonl").write_text(
                json.dumps({"session_id": "new", "reviewed_at": "2026-11-04 09:00:00", "status": "ok", "bewertung": {"kategorie": "falsch_oder_unklar", "schwere": 3, "thema": "Adresse", "begruendung": "Falsch.", "kb_vorschlag": None, "auszug": ["Antwort"]}}) + "\n",
                encoding="utf-8",
            )
            db_path = root / "wiesel.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, created_at DATETIME)")
            conn.execute("INSERT INTO chat_messages VALUES (1, 'new', 'user', 'Frage', '2026-11-04 08:58:00')")
            conn.commit()
            conn.close()

            result = review_api.load_evaluations(evaluations, db_path, datetime(2026, 11, 4).date())

        self.assertEqual([item["session_id"] for item in result], ["new"])
        self.assertEqual(result[0]["letzte_nachricht_am"], "2026-11-04 08:58:00")
        self.assertEqual(result[0]["kategorie"], "falsch_oder_unklar")
        self.assertEqual(result[0]["auszug"], ["Antwort"])

    def test_load_session_messages_masks_email_and_matrikelnummer(self):
        review_api = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "wiesel.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, created_at DATETIME)")
            conn.execute("INSERT INTO chat_messages VALUES (1, 'case-1', 'user', 'Mail test@example.org, Matrikelnummer 12345678', '2026-11-04 08:00:00')")
            conn.execute("INSERT INTO chat_messages VALUES (2, 'case-1', 'assistant', 'Antwort', '2026-11-04 08:01:00')")
            conn.commit()
            conn.close()

            result = review_api.load_session_messages(db_path, "case-1")

        self.assertEqual(result[0]["rolle"], "user")
        self.assertEqual(result[0]["text"], "Mail [E-Mail entfernt], Matrikelnummer [Matrikelnummer entfernt]")
        self.assertEqual(result[1]["zeitstempel"], "2026-11-04 08:01:00")


if __name__ == "__main__":
    unittest.main()
