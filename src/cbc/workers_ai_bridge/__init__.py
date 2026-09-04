"""Anthropic Messages API ↔ Cloudflare Workers AI adapter.

Claude Code only speaks `/v1/messages`. Free `@cf/` models only speak
`/ai/run` or OpenAI `/chat/completions`. This package is the translator.
"""

from cbc.workers_ai_bridge.translate import (
    anthropic_to_openai_messages,
    anthropic_to_run_messages,
    openai_to_anthropic_response,
    run_to_anthropic_response,
)

__all__ = [
    "anthropic_to_openai_messages",
    "anthropic_to_run_messages",
    "openai_to_anthropic_response",
    "run_to_anthropic_response",
]
