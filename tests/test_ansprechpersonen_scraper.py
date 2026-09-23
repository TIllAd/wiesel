"""Regression tests for publicly listed WiSo professor contacts."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from scraper.ansprechpersonen_scraper import extract_public_contact, render


class AnsprechpartnerScraperTests(unittest.TestCase):
    def test_extracts_email_and_phone_from_public_profile_contact_section(self):
        profile_html = """
        <main>
          <h1>Prof. Dr. Nicole Kimmelmann</h1>
          <section class="profile-contact">
            <h2>Kontakt</h2>
            <a href="mailto:nicole.kimmelmann@fau.de">nicole.kimmelmann@fau.de</a>
            <li class="phone">Telefon: +49 911 5302-96298</li>
          </section>
        </main>
        """

        self.assertEqual(
            extract_public_contact(profile_html),
            ("nicole.kimmelmann@fau.de", "+49 911 5302-96298"),
        )

    def test_renders_public_professor_contact_in_knowledge_base(self):
        knowledge_base = render([
            (
                "Prof. Dr. Nicole Kimmelmann",
                "Wirtschaftspädagogik",
                "https://example.test/nicole-kimmelmann/",
                "nicole.kimmelmann@fau.de",
                "+49 911 5302-96298",
            )
        ])

        self.assertIn("E-Mail: nicole.kimmelmann@fau.de", knowledge_base)
        self.assertIn("Telefon: +49 911 5302-96298", knowledge_base)


if __name__ == "__main__":
    unittest.main()
