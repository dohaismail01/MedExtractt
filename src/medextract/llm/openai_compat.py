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
        base = {
            "model": self.cfg.model,
            "temperature": 0,
            "max_tokens": self.cfg.llm_max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # Prefer strict JSON mode, but some models (e.g. gpt-oss on Groq) reject it
        # on complex inputs with `json_validate_failed`. Fall back to plain mode and
        # let validate.py/repair.py extract the JSON object from the response.
        for response_format in ({"type": "json_object"}, None):
            payload = dict(base)
            if response_format:
                payload["response_format"] = response_format
            try:
                resp = httpx.post(url, json=payload, headers=headers,
                                  timeout=self.cfg.llm_timeout_s)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except httpx.TimeoutException as e:
                raise LLMTimeout(str(e)) from e
            except httpx.HTTPStatusError as e:
                text = e.response.text if e.response is not None else ""
                if (response_format is not None
                        and e.response is not None
                        and e.response.status_code == 400
                        and "json_validate_failed" in text):
                    continue  # retry once without strict JSON mode
                raise LLMError(f"LLM HTTP {e.response.status_code}: {text[:300]}") from e
            except httpx.HTTPError as e:
                raise LLMError(f"LLM request failed: {e}") from e
            except (KeyError, IndexError) as e:
                raise LLMError(f"unexpected LLM response shape: {e}") from e
        raise LLMError("LLM request failed: JSON mode rejected and fallback exhausted")
