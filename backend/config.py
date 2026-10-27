"""Shared Anthropic model and pricing configuration."""
from __future__ import annotations

import os
from typing import Final

ANTHROPIC_MODEL: Final = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5").strip()
ANTHROPIC_REVIEW_MODEL: Final = os.getenv("ANTHROPIC_REVIEW_MODEL", ANTHROPIC_MODEL).strip()
PROMPT_TIER_THRESHOLD: Final = 100_000

# USD per million tokens. Haiku 5.5 switches all token categories to the high
# tier once input + cache-write + cache-read tokens exceed 100k.
MODEL_PRICING: Final = {
    "claude-haiku-5-5": {
        "low": {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01},
        "high": {"input": 0.50, "output": 2.50, "cache_write": 0.625, "cache_read": 0.05},
        "tiered": True,
    },
    "claude-haiku-4-5-20251001": {
        "low": {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
        "high": {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
        "tiered": False,
    },
    # Older deployment shorthand remains valid for an emergency rollback.
    "claude-haiku-4-5": {
        "low": {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
        "high": {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
        "tiered": False,
    },
}


def prompt_tokens(input_tokens: int = 0, cache_creation_input_tokens: int = 0, cache_read_input_tokens: int = 0) -> int:
    return max(0, input_tokens) + max(0, cache_creation_input_tokens) + max(0, cache_read_input_tokens)


def pricing_for(model: str, prompt_token_count: int) -> dict[str, float]:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["claude-haiku-5-5"])
    tier = "high" if pricing["tiered"] and prompt_token_count > PROMPT_TIER_THRESHOLD else "low"
    return pricing[tier]


def estimate_cost_usd(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    rates = pricing_for(model, prompt_tokens(input_tokens, cache_creation_input_tokens, cache_read_input_tokens))
    return (
        max(0, input_tokens) * rates["input"]
        + max(0, output_tokens) * rates["output"]
        + max(0, cache_creation_input_tokens) * rates["cache_write"]
        + max(0, cache_read_input_tokens) * rates["cache_read"]
    ) / 1_000_000
