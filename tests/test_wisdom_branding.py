"""Regression checks for the visible Wisdom branding."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "backend" / "static"


class WisdomBrandingTests(unittest.TestCase):
    def test_chat_ui_uses_wisdom_avatar(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")

        self.assertIn("wisdom-compass.png", chat)
        self.assertNotIn("wiesel_standing.png", chat)
        self.assertNotIn("makeWieselSVG", chat)

    def test_all_ui_languages_name_the_bot_wisdom(self):
        strings = (STATIC / "strings.js").read_text(encoding="utf-8")

        self.assertIn("Wisdom", strings)
        self.assertNotIn("Wiesel", strings)

    def test_system_prompt_introduces_wisdom_as_navigator(self):
        prompt = (ROOT / "system-prompt.md").read_text(encoding="utf-8")

        self.assertIn("Ich bin Wisdom", prompt)
        self.assertIn("Navigator", prompt)
        self.assertNotIn("R2-D2", prompt)

    def test_backend_metadata_and_public_fallback_use_wisdom(self):
        backend = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")

        self.assertIn('title="Wisdom Backend"', backend)
        self.assertIn('BUDGET_EXCEEDED_FALLBACK = "Wisdom ist gerade nicht erreichbar.', backend)
        self.assertNotIn('Wiesel macht gerade eine Zwangspause', backend)
        self.assertNotIn('Du bist Wiesel, ein Studienbegleiter', backend)


if __name__ == "__main__":
    unittest.main()
