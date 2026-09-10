"""Thin LLM wrapper over an OpenAI-compatible endpoint (Plan §5.2).

Groq and Ollama both speak the OpenAI chat-completions API, so swapping
providers is a base_url + model change and nothing else. Adds:
  - retry with exponential backoff + jitter on 429/5xx (rate limits are the
    real constraint, not cost);
  - pinned decoding params (temperature/top_p/seed) identical across versions;
  - an on-disk response cache keyed by sha256(model + params + messages), so
    `run_eval.py --from-cache` regenerates the table with zero network calls.
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from functools import lru_cache
from typing import Any, Optional

from openai import APIStatusError, OpenAI, RateLimitError

from . import config


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    if config.PROVIDER == "ollama":
        return OpenAI(base_url=config.OLLAMA_BASE_URL, api_key="ollama")
    return OpenAI(
        base_url=config.GROQ_BASE_URL,
        api_key=config.GROQ_API_KEY,
        timeout=config.REQUEST_TIMEOUT_S,
    )


# --- Disk cache ---------------------------------------------------------------

def _cache_key(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_path(key: str):
    return config.EVAL_CACHE_DIR / f"{key}.json"


def _cache_get(key: str) -> Optional[str]:
    if not config.ENABLE_CACHE:
        return None
    path = _cache_path(key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["content"]
    return None


def _cache_put(key: str, content: str) -> None:
    if not config.ENABLE_CACHE:
        return
    config.EVAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(key).write_text(json.dumps({"content": content}), encoding="utf-8")


# --- Retry --------------------------------------------------------------------

def _with_backoff(fn):
    """Call fn(), retrying on 429/5xx with exponential backoff + jitter."""
    last: Exception | None = None
    for attempt in range(config.HTTP_MAX_RETRIES + 1):
        try:
            return fn()
        except (RateLimitError, APIStatusError) as exc:
            status = getattr(exc, "status_code", None)
            if status is not None and status < 500 and status != 429:
                raise  # non-retryable client error
            last = exc
            if attempt == config.HTTP_MAX_RETRIES:
                break
            delay = min(config.BACKOFF_CAP_S, config.BACKOFF_BASE_S * (2 ** attempt))
            delay *= 1 + random.uniform(-config.BACKOFF_JITTER, config.BACKOFF_JITTER)
            time.sleep(max(0.0, delay))
    raise last  # type: ignore[misc]


# --- Public API ---------------------------------------------------------------

def chat(
    messages: list[dict[str, str]],
    *,
    fast: bool = False,
    json_mode: bool = True,
    max_tokens: Optional[int] = None,
    temperature: float = config.TEMPERATURE,
) -> str:
    """Single chat completion (cached). Returns the raw assistant content."""
    model = config.resolved_model(fast=fast)
    params: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": config.TOP_P,
        "seed": config.SEED,
    }
    if max_tokens:
        params["max_tokens"] = max_tokens
    if json_mode:
        params["response_format"] = {"type": "json_object"}

    key = _cache_key(params)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    if config.CACHE_ONLY:
        raise RuntimeError("cache miss under --from-cache (no network calls allowed)")

    resp = _with_backoff(lambda: _client().chat.completions.create(**params))
    content = resp.choices[0].message.content or ""
    _cache_put(key, content)
    return content


def chat_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    fast: bool = False,
    temperature: float = config.TEMPERATURE,
) -> Any:
    """Chat completion that may emit tool calls. Not cached (has side effects
    downstream). Returns the raw message object for `.tool_calls` inspection."""
    return _with_backoff(lambda: _client().chat.completions.create(
        model=config.resolved_model(fast=fast),
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
        top_p=config.TOP_P,
        seed=config.SEED,
    )).choices[0].message


def client() -> OpenAI:
    """The underlying OpenAI-compatible client, for the agent's tool-calling loop."""
    return _client()


def create_with_backoff(**params):
    """Raw chat-completions call with retry/backoff. Used by the agent loop."""
    return _with_backoff(lambda: _client().chat.completions.create(**params))


def parse_json(content: str) -> Optional[dict]:
    """Best-effort parse of a model reply into a dict, tolerating code fences
    and prose preamble. Returns None on failure."""
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"): text.rfind("}") + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        # Last resort: grab the outermost braces.
        try:
            data = json.loads(content[content.find("{"): content.rfind("}") + 1])
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return None


def health() -> dict[str, Any]:
    """Provider reachability + resolved model, for GET /health."""
    info = {
        "provider": config.PROVIDER,
        "model": config.resolved_model(),
        "configured": config.provider_configured(),
        "reachable": False,
        "error": None,
    }
    if not config.provider_configured():
        info["error"] = "provider not configured (missing API key)"
        return info
    try:
        _client().models.list()
        info["reachable"] = True
    except Exception as exc:  # noqa: BLE001 - health check reports any failure
        info["error"] = str(exc)
    return info
