"""Stage 1: extraction. One LLM call, returns raw text; parsing is the
validator's job (CLAUDE.md §3.1)."""

from __future__ import annotations

from ..config import Settings
from ..llm.base import LLMClient
from ..prompts import get_prompt

_SYSTEM = "You output only valid JSON. No markdown, no commentary."


def run_extract(note: str, client: LLMClient, cfg: Settings) -> str:
    prompt = get_prompt("extraction", cfg.prompt_version).replace("{note}", note)
    return client.complete(_SYSTEM, prompt)
