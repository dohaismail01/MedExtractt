"""OpenAI-compatible client (Groq / Together / vLLM / OpenAI)."""

from __future__ import annotations

import httpx

from ..config import Settings
from .base import LLMError, LLMTimeout


class OpenAICompatClient:
    name = "openai_compat"

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        if not cfg.llm_base_url or not cfg.model:
            raise LLMError("openai_compat requires MEDEXTRACT_LLM_BASE_URL and MEDEXTRACT_MODEL")

    def complete(self, system: str, user: str) -> str:
        url = f"{self.cfg.llm_base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.cfg.llm_api_key:
            headers["Authorization"] = f"Bearer {self.cfg.llm_api_key}"
        payload = {
            "model": self.cfg.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=self.cfg.llm_timeout_s)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException as e:
            raise LLMTimeout(str(e)) from e
        except httpx.HTTPError as e:
            raise LLMError(f"LLM request failed: {e}") from e
        except (KeyError, IndexError) as e:
            raise LLMError(f"unexpected LLM response shape: {e}") from e
