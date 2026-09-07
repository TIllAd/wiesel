"""Regression checks for the internal flag-review controls."""

from pathlib import Path
import unittest


REPORTS = Path(__file__).resolve().parents[1] / "backend" / "static" / "docs" / "internal" / "reports.html"


class InternalReportsFilterTests(unittest.TestCase):
    def test_reports_offer_tag_filters_and_newest_first_sorting(self):
        page = REPORTS.read_text(encoding="utf-8")

        self.assertIn('id="flag-filter"', page)
        self.assertIn("technisches_problem: 'Technisches Problem'", page)
        self.assertIn("sonstiges: 'Sonstiges'", page)
        self.assertIn('id="sort-order"', page)
        self.assertIn('value="newest"', page)
        self.assertIn('value="oldest"', page)
        self.assertIn("function visibleSessions", page)
        self.assertIn("function sortSessions", page)


if __name__ == "__main__":
    unittest.main()
