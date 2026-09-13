"""LLMClient protocol + factory (SPEC.md §8).

The client is an adapter: pipeline code depends only on ``LLMClient.complete``.
The ``stub`` provider is deterministic and offline so the test-suite and a
zero-config run still exercise the whole pipeline.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..config import Settings, settings as default_settings


class LLMError(RuntimeError):
    pass


class LLMTimeout(LLMError):
    pass


@runtime_checkable
class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str:
        """Return the assistant message text for a system+user prompt."""
        ...


def get_client(cfg: Settings | None = None) -> LLMClient:
    cfg = cfg or default_settings
    if cfg.llm_provider == "openai_compat":
        from .openai_compat import OpenAICompatClient

        return OpenAICompatClient(cfg)
    if cfg.llm_provider == "ollama":
        from .ollama import OllamaClient

        return OllamaClient(cfg)
    from .stub import StubClient

    return StubClient(cfg)
