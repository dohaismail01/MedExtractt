"""OpenAI-compatible client (Groq / Together / vLLM / OpenAI)."""

from __future__ import annotations

import time

import httpx

from ..config import Settings
from .base import LLMError, LLMTimeout


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    """Seconds to wait per the provider, from the Retry-After header (integer
    seconds), else None."""
    val = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
    if val:
        try:
            return float(val)
        except ValueError:
            return None
    return None


class OpenAICompatClient:
    name = "openai_compat"

    # Status codes worth retrying: rate limit + transient server errors.
    _RETRYABLE = {429, 500, 502, 503, 504}

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        if not cfg.llm_base_url or not cfg.model:
            raise LLMError("openai_compat requires MEDEXTRACT_LLM_BASE_URL and MEDEXTRACT_MODEL")

    def _post(self, url: str, payload: dict, headers: dict) -> httpx.Response:
        """POST with bounded backoff on transient failures:
          * retryable HTTP status (429 / 5xx) — honoring Retry-After when present;
          * transient transport errors (e.g. "server disconnected", connection
            reset) — these are NOT status codes, so they are retried here too.
        Backoff is exponential, capped at llm_retry_max_delay. A socket timeout
        still maps to LLMTimeout (no retry, so the 504 contract is unchanged).
        Returns the final Response (the caller calls raise_for_status())."""
        delay = self.cfg.llm_retry_base_delay
        last: httpx.Response | None = None
        for attempt in range(self.cfg.llm_max_retries + 1):
            last_attempt = attempt >= self.cfg.llm_max_retries
            try:
                resp = httpx.post(url, json=payload, headers=headers,
                                  timeout=self.cfg.llm_timeout_s)
            except httpx.TimeoutException as e:
                raise LLMTimeout(str(e)) from e
            except httpx.TransportError as e:
                # transient network/protocol error (connection dropped, reset, ...)
                if last_attempt:
                    raise LLMError(f"LLM request failed after {attempt + 1} attempts: {e}") from e
                time.sleep(min(delay, self.cfg.llm_retry_max_delay))
                delay *= 2
                continue
            last = resp
            if resp.status_code in self._RETRYABLE and not last_attempt:
                wait = _retry_after_seconds(resp)
                wait = min(wait if wait is not None else delay, self.cfg.llm_retry_max_delay)
                time.sleep(wait)
                delay *= 2
                continue
            return resp
        return last  # type: ignore[return-value]  # loop runs at least once

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
                resp = self._post(url, payload, headers)  # retries 429/5xx with backoff
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
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
