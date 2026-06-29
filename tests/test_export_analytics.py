import importlib
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


def import_export_analytics(repo_root: Path):
    sys.path.insert(0, str(repo_root))
    try:
        sys.modules.pop("export_analytics", None)
        return importlib.import_module("export_analytics")
    finally:
        sys.path.remove(str(repo_root))


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 29, 12, 0, 0)


def create_db(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            user_name TEXT,
            course_name TEXT,
            created_at TEXT
        );
        CREATE TABLE chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT
        );
        CREATE TABLE llm_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_creation_input_tokens INTEGER,
            cache_read_input_tokens INTEGER,
            estimated_cost_usd REAL,
            estimated_cost_eur REAL,
            latency_ms INTEGER,
            error_type TEXT,
            created_at TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO sessions (id, user_name, course_name, created_at) VALUES (?, ?, ?, ?)",
        [
            ("today", "Heute", "Kurs", "2026-06-29T08:00:00"),
            ("yesterday", "Gestern", "Kurs", "2026-06-28T08:00:00"),
        ],
    )
    conn.executemany(
        "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        [
            ("today", "user", "heute frage", "2026-06-29T08:01:00"),
            ("today", "assistant", "heute antwort", "2026-06-29T08:01:01"),
            ("yesterday", "user", "gestern frage", "2026-06-28T08:01:00"),
            ("yesterday", "assistant", "gestern antwort", "2026-06-28T08:01:01"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO llm_usage (
            session_id, model, input_tokens, output_tokens,
            cache_creation_input_tokens, cache_read_input_tokens,
            estimated_cost_usd, estimated_cost_eur, latency_ms, error_type, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("today", "model-a", 10, 5, 100, 0, 0.01, 0.009, 1000, None, "2026-06-29T08:01:01"),
            ("yesterday", "model-a", 20, 5, 200, 0, 0.02, 0.018, 2000, None, "2026-06-28T08:01:01"),
        ],
    )
    conn.commit()
    conn.close()


class ExportAnalyticsTests(unittest.TestCase):
    def test_export_defaults_to_only_current_calendar_day(self):
        repo_root = Path(__file__).resolve().parents[1]
        module = import_export_analytics(repo_root)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_repo = tmp_path / "repo"
            fake_repo.mkdir()
            (fake_repo / "docs").mkdir()

            db_path = tmp_path / "wiesel.db"
            output_dir = tmp_path / "analytics"
            create_db(db_path)

            module.DB_PATH = db_path
            module.OUTPUT_DIR = output_dir
            module.__file__ = str(fake_repo / "export_analytics.py")
            module.datetime = FixedDateTime
            module.UPDATE_DOCS = False

            module.export()

            data = json.loads((output_dir / "analytics_2026-06-29.json").read_text(encoding="utf-8"))

            self.assertEqual(data["periode"], "Tagesexport 2026-06-29")
            self.assertEqual([s["session_id"] for s in data["sessions"]], ["today"])
            self.assertEqual(data["statistik"]["sessions_gesamt"], 1)
            self.assertEqual(data["llm_usage"]["requests_gesamt"], 1)
            self.assertEqual(data["llm_usage"]["cache_write_requests"], 1)
            self.assertNotIn("kosten_modell", data)


if __name__ == "__main__":
    unittest.main()
