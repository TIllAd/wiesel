"""Unit tests for the deterministic daily Wisdom chat-review job."""
from __future__ import annotations

import importlib.util
import inspect
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "backend" / "jobs" / "chat_review.py"


def load_module():
    spec = importlib.util.spec_from_file_location("chat_review_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_db(path: Path, now: datetime) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sessions (id TEXT PRIMARY KEY, created_at DATETIME, last_accessed DATETIME);
        CREATE TABLE chat_messages (
            id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, created_at DATETIME
        );
        CREATE TABLE llm_usage (
            id INTEGER PRIMARY KEY, session_id TEXT, model TEXT, input_tokens INTEGER,
            output_tokens INTEGER, cache_creation_input_tokens INTEGER,
            cache_read_input_tokens INTEGER, estimated_cost_usd REAL, estimated_cost_eur REAL,
            latency_ms INTEGER, error_type TEXT, usage_type TEXT, created_at DATETIME
        );
        """
    )
    records = [
        ("complete", now - timedelta(hours=2), now - timedelta(hours=2)),
        ("active", now - timedelta(hours=1), now - timedelta(hours=1)),
        ("bot-only", now - timedelta(hours=2), now - timedelta(hours=2)),
        ("already-done", now - timedelta(hours=2), now - timedelta(hours=2)),
        ("old", now - timedelta(days=3), now - timedelta(days=3)),
    ]
    records = [(session_id, created.isoformat(sep=" "), accessed.isoformat(sep=" ")) for session_id, created, accessed in records]
    conn.executemany("INSERT INTO sessions VALUES (?, ?, ?)", records)
    messages = [
        (1, "complete", "user", "synthetic user message", now - timedelta(hours=2)),
        (2, "complete", "assistant", "synthetic bot response", now - timedelta(hours=2, minutes=-1)),
        (3, "active", "user", "still active", now - timedelta(minutes=10)),
        (4, "bot-only", "assistant", "no user message", now - timedelta(hours=2)),
        (5, "already-done", "user", "previously evaluated", now - timedelta(hours=2)),
        (6, "old", "user", "retrospective candidate", now - timedelta(days=3)),
    ]
    messages = [(message_id, session_id, role, content, created.isoformat(sep=" ")) for message_id, session_id, role, content, created in messages]
    conn.executemany("INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)", messages)
    conn.commit()
    conn.close()


class ChatReviewTests(unittest.TestCase):
    def test_selection_requires_inactive_session_user_message_and_new_state(self):
        review = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime(2026, 10, 20, 12, 0, 0)
            db_path = Path(tmp) / "test.db"
            make_db(db_path, now)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            selected = review.select_sessions(conn, {"already-done"}, now - timedelta(minutes=30))
            conn.close()

        self.assertEqual([session["id"] for session in selected], ["complete", "old"])

    def test_selection_since_limits_retrospective_run_by_last_message_date(self):
        review = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime(2026, 10, 20, 12, 0, 0)
            db_path = Path(tmp) / "test.db"
            make_db(db_path, now)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            selected = review.select_sessions(conn, set(), now - timedelta(minutes=30), datetime(2026, 10, 19))
            conn.close()

        self.assertEqual([session["id"] for session in selected], ["complete", "already-done"])

    def test_selection_since_includes_an_old_session_with_a_new_message(self):
        review = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime(2026, 10, 20, 12, 0, 0)
            db_path = Path(tmp) / "test.db"
            make_db(db_path, now)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)",
                (7, "old", "assistant", "follow-up after the cutoff", "2026-10-19 08:00:00"),
            )
            conn.commit()
            conn.row_factory = sqlite3.Row
            selected = review.select_sessions(conn, set(), now - timedelta(minutes=30), datetime(2026, 10, 19))
            conn.close()

        self.assertIn("old", [session["id"] for session in selected])

    def test_claude_request_kwargs_bind_to_installed_anthropic_messages_signature(self):
        review = load_module()
        import anthropic

        kwargs = review.claude_request_kwargs("synthetic prompt", max_tokens=420)
        inspect.signature(anthropic.resources.messages.Messages.create).bind(None, **kwargs)
        self.assertNotIn("temperature", kwargs)

    def test_state_round_trip_and_missing_state_are_safe(self):
        review = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.assertEqual(review.load_reviewed_ids(directory), set())
            review.save_reviewed_ids(directory, {"session-b", "session-a"})
            self.assertEqual(review.load_reviewed_ids(directory), {"session-a", "session-b"})
            stored = json.loads((directory / "review_state.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["reviewed_session_ids"], ["session-a", "session-b"])

    def test_parse_json_response_accepts_string_or_string_list_excerpt_and_null_proposal(self):
        review = load_module()
        raw = """```json
        {"kategorie":"wissensluecke","schwere":2,"thema":"Frist","begruendung":"Antwort blieb vage.","kb_vorschlag":null,"auszug":["Kurzes Zitat eins", "Kurzes Zitat zwei"]}
        ```"""
        result = review.parse_json_response(raw)
        self.assertEqual(result["kategorie"], "wissensluecke")
        self.assertEqual(result["schwere"], 2)
        self.assertIsNone(result["kb_vorschlag"])
        self.assertEqual(result["auszug"], ["Kurzes Zitat eins", "Kurzes Zitat zwei"])
        single_excerpt = review.parse_json_response(
            '{"kategorie":"unauffaellig","schwere":0,"thema":"Keins","begruendung":"Unauffällig.","kb_vorschlag":null,"auszug":"Ein kurzes Zitat"}'
        )
        self.assertEqual(single_excerpt["auszug"], ["Ein kurzes Zitat"])

    def test_parse_json_response_rejects_invalid_json_with_raw_response(self):
        review = load_module()
        with self.assertRaises(review.ReviewJSONError) as error:
            review.parse_json_response("not json")
        self.assertEqual(error.exception.raw_response, "not json")
        with self.assertRaises(review.ReviewJSONError):
            review.parse_json_response('{"kategorie":"erfunden"}')
    def test_run_writes_external_artifacts_and_second_run_skips_reviewed_sessions(self):
        review = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "test.db"
            report_dir = root / "reports"
            now = datetime(2026, 10, 20, 12, 0, 0)
            make_db(db_path, now)
            calls = []

            def fake_evaluate(_conn, _conversation):
                calls.append("map")
                return {
                    "kategorie": "wissensluecke", "schwere": 1, "thema": "Testthema",
                    "begruendung": "Synthetic finding.", "kb_vorschlag": "Synthetic proposal.",
                    "auszug": "Synthetic quote.",
                }, {"input_tokens": 10, "output_tokens": 5, "cost_eur": 0.001}

            review.evaluate_session = fake_evaluate
            review.reduce_review = lambda _conn, _items, _count: ("# Kurzüberblick\nSynthetischer Test.", {"input_tokens": 5, "output_tokens": 4, "cost_eur": 0.002})
            first = review.run_review(db_path, report_dir, since=datetime(2026, 10, 20), now=now)
            second = review.run_review(db_path, report_dir, since=datetime(2026, 10, 20), now=now + timedelta(minutes=1))

            self.assertEqual(first["reviewed"], 2)
            self.assertEqual(second["selected"], 0)
            self.assertEqual(calls, ["map", "map"])
            self.assertTrue((report_dir / "evaluations" / "2026-10-20.jsonl").exists())
            report = (report_dir / "reviews" / "2026-10-20.md").read_text(encoding="utf-8")
            self.assertIn("Tokenverbrauch dieses Laufs", report)
            self.assertIn("Geschätzte Kosten dieses Laufs", report)

    def test_failed_session_is_not_saved_in_state_and_is_selected_again(self):
        review = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "test.db"
            report_dir = root / "reports"
            now = datetime(2026, 10, 20, 12, 0, 0)
            make_db(db_path, now)
            review.evaluate_session = lambda _conn, _conversation: (_ for _ in ()).throw(review.ReviewJSONError("bad json"))

            with self.assertRaises(review.AllEvaluationsFailed):
                review.run_review(db_path, report_dir, since=datetime(2026, 10, 20), now=now)
            state = review.load_state(report_dir)
            second = review.run_review(db_path, report_dir, since=datetime(2026, 10, 20), dry_run=True, now=now)

        self.assertEqual(state["reviewed_session_ids"], [])
        self.assertEqual(second["selected"], 2)

    def test_review_json_error_jsonl_contains_truncated_raw_model_response(self):
        review = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "test.db"
            report_dir = root / "reports"
            now = datetime(2026, 10, 20, 12, 0, 0)
            make_db(db_path, now)
            raw = "x" * 700
            review.evaluate_session = lambda _conn, _conversation: (_ for _ in ()).throw(
                review.ReviewJSONError("invalid schema", raw_response=raw)
            )

            with self.assertRaises(review.AllEvaluationsFailed):
                review.run_review(db_path, report_dir, since=datetime(2026, 10, 20), now=now)
            records = [
                json.loads(line)
                for line in (report_dir / "evaluations" / "2026-10-20.jsonl").read_text(encoding="utf-8").splitlines()
            ]

        self.assertTrue(all(record["status"] == "error" for record in records))
        self.assertTrue(all(record["raw_response"] == raw[:500] for record in records))

    def test_non_transient_type_error_aborts_without_retrying_each_session(self):
        review = load_module()
        calls = []

        def broken_claude(_conn, _prompt, *, max_tokens):
            self.assertEqual(max_tokens, 420)
            calls.append("call")
            raise TypeError("unsupported keyword")

        review.claude_text = broken_claude
        with self.assertRaises(TypeError):
            review.evaluate_session(None, "synthetic conversation")

        self.assertEqual(calls, ["call"])

    def test_fatal_error_stops_run_after_first_session_without_state_update(self):
        review = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "test.db"
            report_dir = root / "reports"
            now = datetime(2026, 10, 20, 12, 0, 0)
            make_db(db_path, now)
            calls = []

            def broken_evaluate(_conn, _conversation):
                calls.append("map")
                raise TypeError("unsupported keyword")

            review.evaluate_session = broken_evaluate
            with self.assertRaises(review.FatalReviewError):
                review.run_review(db_path, report_dir, since=datetime(2026, 10, 20), now=now)

            state = review.load_state(report_dir)

        self.assertEqual(calls, ["map"])
        self.assertEqual(state["reviewed_session_ids"], [])


if __name__ == "__main__":
    unittest.main()
