"""Regression checks for the compact, voluntary UEQ-S feedback control."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "backend" / "static"
MAIN = ROOT / "backend" / "main.py"


class UeqSFeedbackTests(unittest.TestCase):
    def test_chat_has_a_compact_opt_in_feedback_control_with_one_item_at_a_time(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")

        self.assertIn('id="ueq-feedback"', chat)
        self.assertIn('id="ueq-feedback-toggle"', chat)
        self.assertIn('id="ueq-feedback-scale"', chat)
        self.assertIn('data-ueq-value="1"', chat)
        self.assertIn('data-ueq-value="7"', chat)
        self.assertIn('id="ueq-feedback-skip"', chat)
        self.assertIn('id="ueq-feedback-close"', chat)
        self.assertIn('Wisdom bewerten!', chat)
        self.assertIn('const UEQ_S_ITEMS = [', chat)
        self.assertIn('renderUeqFeedbackItem()', chat)

    def test_feedback_uses_the_standard_eight_ueq_s_pairs_without_free_text(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")

        self.assertIn("left: 'behindernd', right: 'unterstützend'", chat)
        self.assertIn("left: 'kompliziert', right: 'einfach'", chat)
        self.assertIn("left: 'langweilig', right: 'spannend'", chat)
        self.assertIn("left: 'konventionell', right: 'originell'", chat)
        self.assertIn('UEQ_S_ITEMS.length', chat)
        self.assertNotIn('id="ueq-feedback-comment"', chat)

    def test_feedback_explains_the_scale_in_german_and_ends_with_a_closable_thank_you(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        strings = (STATIC / "strings.js").read_text(encoding="utf-8")

        self.assertIn('Welche Seite trifft eher zu?', chat)
        self.assertIn('1 = trifft ganz links zu · 7 = trifft ganz rechts zu.', chat)
        self.assertIn("function activeUeqItems() { return UEQ_S_ITEMS; }", chat)
        self.assertNotIn('UEQ_S_ITEMS_EN', chat)
        self.assertIn("function showUeqThanks()", chat)
        self.assertIn("Danke für dein Feedback!", chat)
        self.assertIn("Deine Bewertung wurde gespeichert.", chat)
        self.assertIn(".ueq-feedback-pair[hidden], .ueq-feedback-scale[hidden] { display:none !important; }", chat)
        self.assertIn("close.addEventListener('click'", chat)
        self.assertNotIn("Help us improve Wisdom", strings)
        self.assertNotIn("Thank you for your feedback.", strings)

    def test_mobile_feedback_moves_into_the_utility_bar_and_never_covers_footer_links(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")

        self.assertIn('@media (max-width: 720px)', chat)
        self.assertIn('.fau-utility .ueq-feedback { position:relative;', chat)
        self.assertIn('.fau-utility .ueq-feedback-toggle {', chat)
        self.assertIn('id="ueq-feedback" class="ueq-feedback"', chat)
        self.assertLess(chat.index('id="ueq-feedback"'), chat.index('id="messages"'))
        self.assertNotIn('bottom:18px', chat[chat.index('@media (max-width: 720px)'):])

    def test_skipping_or_completing_feedback_hides_it_for_the_browser_session(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")

        self.assertIn("const UEQ_SESSION_DISMISSED_KEY = `wisdomUeqDismissed:${sessionId}`;", chat)
        self.assertIn('function hideUeqForSession()', chat)
        self.assertIn("sessionStorage.setItem(UEQ_SESSION_DISMISSED_KEY, '1');", chat)
        self.assertIn("sessionStorage.getItem(UEQ_SESSION_DISMISSED_KEY) === '1'", chat)
        self.assertIn("skip.addEventListener('click', hideUeqForSession);", chat)
        self.assertIn('hideUeqForSession();', chat)

    def test_feedback_is_sent_as_minimal_structured_data_to_a_dedicated_endpoint(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        main = MAIN.read_text(encoding="utf-8")

        self.assertIn("fetch('/api/feedback/ueq-s'", chat)
        self.assertIn('JSON.stringify({session_id: sessionId, item_key: item.key, value})', chat)
        self.assertIn('class UeqSFeedback(Base):', main)
        self.assertIn('@app.post("/api/feedback/ueq-s")', main)
        self.assertIn('class UeqSFeedbackRequest(BaseModel):', main)
        self.assertIn('value: int', main)


if __name__ == "__main__":
    unittest.main()
