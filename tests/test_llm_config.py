"""Regression tests for model selection and Haiku pricing tiers."""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "backend" / "config.py"


def load_config():
    spec = importlib.util.spec_from_file_location("llm_config_under_test", CONFIG)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class LLMConfigTests(unittest.TestCase):
    def test_default_model_is_haiku_5_5_and_review_can_override_it(self):
        old_model = os.environ.pop("ANTHROPIC_MODEL", None)
        old_review_model = os.environ.pop("ANTHROPIC_REVIEW_MODEL", None)
        try:
            config = load_config()
            self.assertEqual(config.ANTHROPIC_MODEL, "claude-haiku-5-5")
            self.assertEqual(config.ANTHROPIC_REVIEW_MODEL, "claude-haiku-5-5")
            os.environ["ANTHROPIC_MODEL"] = "claude-haiku-4-5-20251001"
            os.environ["ANTHROPIC_REVIEW_MODEL"] = "review-override"
            config = load_config()
            self.assertEqual(config.ANTHROPIC_MODEL, "claude-haiku-4-5-20251001")
            self.assertEqual(config.ANTHROPIC_REVIEW_MODEL, "review-override")
        finally:
            if old_model is None:
                os.environ.pop("ANTHROPIC_MODEL", None)
            else:
                os.environ["ANTHROPIC_MODEL"] = old_model
            if old_review_model is None:
                os.environ.pop("ANTHROPIC_REVIEW_MODEL", None)
            else:
                os.environ["ANTHROPIC_REVIEW_MODEL"] = old_review_model

    def test_haiku_5_5_uses_high_tier_for_every_token_type_above_100k_prompt_tokens(self):
        config = load_config()
        low = config.estimate_cost_usd(
            "claude-haiku-5-5", input_tokens=99_000, output_tokens=1_000,
            cache_creation_input_tokens=500, cache_read_input_tokens=400,
        )
        high = config.estimate_cost_usd(
            "claude-haiku-5-5", input_tokens=100_000, output_tokens=1_000,
            cache_creation_input_tokens=500, cache_read_input_tokens=400,
        )
        self.assertAlmostEqual(low, 0.0104665)
        self.assertAlmostEqual(high, 0.0528325)

    def test_haiku_4_5_rollback_keeps_legacy_pricing(self):
        config = load_config()
        self.assertAlmostEqual(
            config.estimate_cost_usd("claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=1_000_000),
            6.0,
        )


if __name__ == "__main__":
    unittest.main()
