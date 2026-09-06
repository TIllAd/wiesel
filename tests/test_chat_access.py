"""Regression tests for the public chat entry point."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "backend" / "main.py"


class PublicChatAccessTests(unittest.TestCase):
    def test_chat_page_mints_an_anonymous_public_session_not_a_debug_session(self):
        source = MAIN.read_text(encoding="utf-8")

        self.assertIn("public_session_wisdom_", source)
        self.assertIn('user_id="public_user"', source)
        self.assertNotIn("debug_session_wiesel_", source)
        self.assertNotIn('"debug_user"', source)
        self.assertNotIn("should_mint_debug_session", source)

    def test_chat_page_never_adds_a_debug_query_parameter(self):
        source = MAIN.read_text(encoding="utf-8")

        self.assertNotIn("&debug=1", source)


if __name__ == "__main__":
    unittest.main()
