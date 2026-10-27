"""Count the exact cached Wisdom system prompt with both supported Haiku models."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import anthropic

# The documented invocation runs with /app/backend as cwd; add /app so the
# backend package and its production prompt builder resolve identically.
APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from backend.config import ANTHROPIC_MODEL, PROMPT_TIER_THRESHOLD
from backend.main import build_system_prompt, load_knowledge_base

MODELS = ("claude-haiku-4-5-20251001", "claude-haiku-5-5")


def count_system_prompt_tokens(client: anthropic.Anthropic, model: str) -> int:
    kb_content = load_knowledge_base()
    response = client.messages.count_tokens(
        model=model,
        system=[{"type": "text", "text": build_system_prompt(kb_content), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "Tokenzählung der Wissensbasis."}],
    )
    return int(response.input_tokens)


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY fehlt")
    client = anthropic.Anthropic(api_key=api_key)
    print(f"Aktives Chat-Modell: {ANTHROPIC_MODEL}")
    for model in MODELS:
        tokens = count_system_prompt_tokens(client, model)
        marker = "ÜBER 100k: hohe Preisstaffel" if tokens > PROMPT_TIER_THRESHOLD else "≤100k: niedrige Preisstaffel"
        print(f"{model}: {tokens:,} Prompt-Tokens — {marker}")


if __name__ == "__main__":
    main()
