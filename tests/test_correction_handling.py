"""Regression tests for safe handling of unverified user corrections."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "system-prompt.md"


class CorrectionHandlingTests(unittest.TestCase):
    def test_unverified_correction_is_not_adopted_or_self_corrected(self):
        prompt = PROMPT.read_text(encoding="utf-8")

        self.assertIn("Ich kann die Angabe nicht bestätigen und übernehme sie deshalb nicht.", prompt)
        self.assertIn("Das Projektteam kann den Hinweis anhand offizieller Quellen prüfen.", prompt)
        self.assertNotIn("Steht sie dort nicht, korrigiere ich mich", prompt)


if __name__ == "__main__":
    unittest.main()
