"""Regression tests for the per-request current-date prompt context."""

import asyncio
from datetime import datetime
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]


class CurrentDatetimePromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tempdir = tempfile.TemporaryDirectory()
        cls._previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(cls._tempdir.name) / 'wisdom-test.db'}"
        from backend import main
        cls.main = main

    @classmethod
    def tearDownClass(cls):
        if cls._previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls._previous_database_url
        cls._tempdir.cleanup()

    def test_formats_current_time_in_german_without_container_locale(self):
        current = datetime(2026, 10, 6, 11, 36, tzinfo=self.main.APP_TIMEZONE)

        context = self.main.build_current_datetime_context(current)

        self.assertIn("Dienstag, 06.10.2026, 11:36 Uhr (Europe/Berlin).", context)
        self.assertIn('einzige gültige Angabe für „heute"', context)
        self.assertIn("Liegt eine Frist in der Vergangenheit", context)
        self.assertIn("tagesaktuelle Daten (Mensa, Wetter, ÖPNV)", context)

    def test_adds_fresh_datetime_block_after_the_cached_system_prompt(self):
        captured_calls = []

        async def create(**kwargs):
            captured_calls.append(kwargs)
            return type("Response", (), {
                "usage": type("Usage", (), {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 100,
                })(),
                "content": [type("Content", (), {"text": "Antwort."})()],
                "stop_reason": "end_turn",
            })()

        fake_client = type("Client", (), {"messages": type("Messages", (), {"create": AsyncMock(side_effect=create)})()})()
        contexts = iter(["Zeit A", "Zeit B"])

        with patch.object(self.main, "_anthropic_client", fake_client), \
             patch.object(self.main, "build_current_datetime_context", side_effect=contexts), \
             patch.object(self.main, "record_llm_usage"):
            asyncio.run(self.main.call_claude("session-1", "Wie spät ist es?", kb_content="Wissensbasis"))
            asyncio.run(self.main.call_claude("session-1", "Und jetzt?", kb_content="Wissensbasis"))

        self.assertEqual(len(captured_calls), 2)
        for expected_context, call in zip(("Zeit A", "Zeit B"), captured_calls):
            blocks = call["system"]
            self.assertEqual(blocks[0]["cache_control"], {"type": "ephemeral"})
            self.assertIn("Wissensbasis", blocks[0]["text"])
            current_context_block = next(block for block in blocks if block["text"] == expected_context)
            self.assertEqual(blocks.index(current_context_block), 1)
            self.assertNotIn("cache_control", current_context_block)


if __name__ == "__main__":
    unittest.main()
