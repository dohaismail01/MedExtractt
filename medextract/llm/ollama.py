"""Ollama client (native /api/chat)."""

from __future__ import annotations

import httpx

from ..config import Settings
from .base import LLMError, LLMTimeout


class OllamaClient:
    name = "ollama"

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.base = (cfg.llm_base_url or "http://localhost:11434").rstrip("/")
        if not cfg.model:
            raise LLMError("ollama requires MEDEXTRACT_MODEL")

    def complete(self, system: str, user: str) -> str:
        url = f"{self.base}/api/chat"
        payload = {
            "model": self.cfg.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = httpx.post(url, json=payload, timeout=self.cfg.llm_timeout_s)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except httpx.TimeoutException as e:
            raise LLMTimeout(str(e)) from e
        except httpx.HTTPError as e:
            raise LLMError(f"LLM request failed: {e}") from e
        except (KeyError, IndexError) as e:
            raise LLMError(f"unexpected Ollama response shape: {e}") from e
