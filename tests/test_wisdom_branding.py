"""Regression checks for the visible Wisdom branding."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "backend" / "static"


class WisdomBrandingTests(unittest.TestCase):
    def test_chat_ui_uses_robot_favicon_for_wisdom_message_avatar(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")

        self.assertIn("const WISDOM_AVATAR = '/static/brand/favicon-180.png';", chat)
        self.assertNotIn("wisdom-label-quadrat.svg", chat)
        self.assertNotIn("wisdom-compass.png", chat)
        self.assertNotIn("wiesel_standing.png", chat)
        self.assertNotIn("makeWieselSVG", chat)

    def test_all_ui_languages_name_the_bot_wisdom(self):
        strings = (STATIC / "strings.js").read_text(encoding="utf-8")

        self.assertIn("Wisdom", strings)
        self.assertNotIn("Wiesel", strings)

    def test_first_visit_disclaimer_requires_acknowledgement_and_persists_it(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")

        self.assertIn('id="wisdom-disclaimer"', chat)
        self.assertIn('id="wisdom-disclaimer-accept"', chat)
        self.assertIn('wisdom_disclaimer_acknowledged', chat)
        self.assertIn('document.cookie', chat)
        self.assertIn('Wichtige Informationen bitte immer in offiziellen Quellen prüfen.', chat)
        self.assertIn('Wisdom kann Fehler machen', chat)

    def test_first_visit_disclaimer_links_to_central_student_advisory_service(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")

        self.assertIn(
            'https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenberatung/zentrale-studienberatung/',
            chat,
        )
        self.assertIn('Zentrale Studienberatung', chat)

    def test_final_brand_assets_replace_placeholder_and_supply_link_metadata(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        brand = STATIC / "brand"

        self.assertIn('/static/brand/wisdom-logo.svg', chat)
        self.assertNotIn('wisdom-lockup-placeholder.svg', chat)
        self.assertIn('rel="icon"', chat)
        self.assertIn('apple-touch-icon', chat)
        self.assertIn('property="og:image"', chat)
        self.assertIn('/static/brand/og-image.png', chat)

        for filename in (
            "wisdom-logo.svg",
            "wisdom-logo-weiss.svg",
            "wisdom-label-quadrat.svg",
            "favicon.ico",
            "favicon-32.png",
            "favicon-180.png",
            "favicon-512.png",
            "og-image.png",
        ):
            self.assertTrue((brand / filename).is_file(), filename)

    def test_ki_transparency_page_and_legal_links_are_shipped(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        strings = (STATIC / "strings.js").read_text(encoding="utf-8")
        transparency = (STATIC / "legal" / "ueber-wisdom.html").read_text(encoding="utf-8")

        self.assertIn('/static/legal/ueber-wisdom.html', chat)
        self.assertIn('id="link-about"', chat)
        self.assertIn("footerAbout: 'Über Wisdom'", strings)
        self.assertIn("Wisdom ist eine KI und kann Fehler machen", strings)
        self.assertIn("Kann Wisdom sich irren?", transparency)
        self.assertIn("Datenschutzerklärung", transparency)

    def test_legal_pages_describe_the_current_public_website_without_lti_data(self):
        legal = STATIC / "legal"
        impressum = (legal / "impressum.html").read_text(encoding="utf-8")
        privacy = (legal / "datenschutz.html").read_text(encoding="utf-8")
        accessibility = (legal / "barrierefreiheit.html").read_text(encoding="utf-8")

        self.assertIn("Freyeslebenstraße 1", impressum)
        self.assertIn("DE 132507686", impressum)
        self.assertIn("wisdom.chatbot-wiso.de", impressum)
        self.assertIn("öffentliche Website", privacy)
        self.assertNotIn("LTI", privacy)
        self.assertIn("keine Nutzerkennungen, Namen oder Kursdaten aus StudOn", privacy)
        self.assertNotIn("vollständiger Name", privacy)
        self.assertIn("Datenschutzerklärung", privacy)
        self.assertNotIn("Entwurf – nicht als finale Datenschutzerklärung veröffentlichen", privacy)
        transparency = (legal / "ueber-wisdom.html").read_text(encoding="utf-8")
        for page in (impressum, privacy, transparency):
            self.assertIn("Professur für Wirtschaftspädagogik", page)
            self.assertNotIn("Lehrstuhl für Wirtschaftspädagogik", page)
        self.assertNotIn("[Datum", accessibility)
        self.assertIn("bitv@bayern.de", accessibility)

    def test_public_architecture_starts_with_the_external_website_not_studon(self):
        architecture = (STATIC / "docs" / "public" / "architecture.html").read_text(encoding="utf-8")

        self.assertIn("Öffentliche Website", architecture)
        self.assertNotIn("StudOn Chat", architecture)
        self.assertNotIn("LTI-Fenster", architecture)

    def test_final_legal_pages_name_responsible_contacts_and_no_longer_present_drafts(self):
        legal = STATIC / "legal"
        privacy = (legal / "datenschutz.html").read_text(encoding="utf-8")
        accessibility = (legal / "barrierefreiheit.html").read_text(encoding="utf-8")
        impressum = (legal / "impressum.html").read_text(encoding="utf-8")

        for page in (privacy, accessibility):
            self.assertNotIn("Arbeitsfassung", page)
            self.assertNotIn("Entwurf", page)
        self.assertIn("datenschutzbeauftragter@fau.de", privacy)
        self.assertIn("Bayerischen Landesbeauftragten für den Datenschutz", privacy)
        self.assertIn("Speicherdauer", privacy)
        self.assertIn("Prof. Dr. Nicole Kimmelmann", impressum)
        self.assertIn("wiso-sekretariat-kimmelmann@fau.de", impressum)
        self.assertIn("Selbstbewertung", accessibility)
        self.assertIn("bitv@bayern.de", accessibility)

    def test_accessibility_statement_is_final_and_transparent_about_its_self_assessment_basis(self):
        accessibility = (STATIC / "legal" / "barrierefreiheit.html").read_text(encoding="utf-8")

        self.assertIn("Prüfgrundlage der Selbstbewertung", accessibility)
        self.assertIn("Selbstbewertung nach BITV 2.0 und WCAG 2.2", accessibility)
        self.assertIn("Prüfdatum: 29. August 2026", accessibility)
        self.assertIn("bekannten Einschränkungen", accessibility)
        self.assertNotIn("vollständig barrierefrei", accessibility)

    def test_footer_credits_nuremberg_and_links_to_the_professorship_contacts(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")

        self.assertIn('id="footer-credit"', chat)
        self.assertIn("♡ Made with love in Nuremberg ♡", chat)
        self.assertIn('href="mailto:wiso-sekretariat-kimmelmann@fau.de"', chat)
        self.assertIn('href="https://www.professur-wirtschaftspaedagogik.rw.fau.de"', chat)

    def test_legal_contact_uses_the_professorship_email_and_website(self):
        legal = STATIC / "legal"
        impressum = (legal / "impressum.html").read_text(encoding="utf-8")

        for filename in (
            "ueber-wisdom.html",
            "impressum.html",
            "datenschutz.html",
            "barrierefreiheit.html",
        ):
            page = (legal / filename).read_text(encoding="utf-8")
            self.assertIn("wiso-sekretariat-kimmelmann@fau.de", page)
            self.assertNotIn("lehre-digital@fau.de", page)

        self.assertIn("<h2>Professur für Wirtschaftspädagogik</h2>", impressum)
        self.assertNotIn("Projekt und redaktionelle Verantwortung", impressum)
        self.assertIn("https://www.professur-wirtschaftspaedagogik.rw.fau.de", impressum)

    def test_language_switch_offers_only_german_and_english_ui_copy(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        strings = (STATIC / "strings.js").read_text(encoding="utf-8")

        self.assertIn("const SUPPORTED_LANGS = ['de', 'en'];", chat)
        self.assertIn("const LANG_LABELS = { de: 'DE', en: 'EN' };", chat)
        self.assertIn("const LANG_NAMES  = { de: 'Deutsch', en: 'English' };", chat)
        self.assertNotIn("\n  es: {", strings)
        self.assertNotIn("\n  it: {", strings)
        self.assertNotIn("\n  zh: {", strings)

    def test_mentor_flagging_control_is_explanatory_and_visible_in_the_utility_bar(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        strings = (STATIC / "strings.js").read_text(encoding="utf-8")

        self.assertIn('class="chat-flag-label" id="chat-flag-label"', chat)
        self.assertIn('class="sr-only chat-flag-hint" id="chat-flag-hint"', chat)
        self.assertIn('aria-describedby="chat-flag-hint"', chat)
        self.assertIn('min-height:36px', chat)
        self.assertIn("flagBtn: 'Testfall markieren'", strings)
        self.assertIn("flagHint: 'Für Mentor:innen: auffällige oder unklare Antworten für die Auswertung markieren.'", strings)

    def test_mentor_flagging_collects_a_reason_without_a_github_contribution_link(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        strings = (STATIC / "strings.js").read_text(encoding="utf-8")

        self.assertNotIn("github.com/TIllAd/wiesel/issues/new", chat)
        self.assertNotIn('id="knowledge-link"', chat)
        self.assertIn('id="flag-reasons"', chat)
        self.assertIn('data-flag-reason', chat)
        self.assertIn("tag: reason", chat)
        self.assertIn("let flagRequestPending = false;", chat)
        self.assertIn("if (flagRequestPending || btn.classList.contains('flagged')) return;", chat)
        self.assertIn("options.forEach(option => { option.disabled = true; });", chat)
        self.assertIn("flagReasonPrompt: 'Was ist auffällig?'", strings)
        self.assertIn("flagReasonIncorrect: 'Falsche Information'", strings)
        self.assertIn("flagReasonTechnical: 'Technisches Problem'", strings)
        self.assertNotIn("knowledgeContribute:", strings)

    def test_quick_question_bar_does_not_offer_the_planspiel(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        strings = (STATIC / "strings.js").read_text(encoding="utf-8")

        self.assertNotIn('id="quick-planspiel"', chat)
        self.assertNotIn("quickPlanspielLabel:", strings)
        self.assertNotIn("quickPlanspielPrompt:", strings)

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
