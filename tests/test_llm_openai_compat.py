"""OpenAI-compatible client: transient-error retry with backoff.

Hermetic - httpx.post is patched to a scripted sequence of responses and
time.sleep is patched to a no-op, so no network call and no real delay.
"""

import httpx
import pytest

from medextract.config import get_settings
from medextract.llm import openai_compat as oc
from medextract.llm.base import LLMError, LLMTimeout


def _cfg(**over):
    base = dict(llm_provider="openai_compat", model="test-model",
                llm_base_url="https://example.test/v1", llm_api_key="k",
                llm_max_retries=3, llm_retry_base_delay=0.01, llm_retry_max_delay=0.02)
    base.update(over)
    return get_settings().model_copy(update=base)


def _resp(status, body=None, headers=None):
    return httpx.Response(status, json=body if body is not None else {}, headers=headers or {},
                          request=httpx.Request("POST", "https://example.test/v1/chat/completions"))


def _patch_sequence(monkeypatch, responses):
    calls = {"n": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        r = responses[i]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(oc.httpx, "post", fake_post)
    monkeypatch.setattr(oc.time, "sleep", lambda s: None)  # no real backoff wait
    return calls


_OK = {"choices": [{"message": {"content": '{"symptoms": []}'}}]}


def test_retries_then_succeeds(monkeypatch):
    calls = _patch_sequence(monkeypatch, [_resp(429), _resp(429), _resp(200, _OK)])
    out = oc.OpenAICompatClient(_cfg()).complete("sys", "user")
    assert out == '{"symptoms": []}'
    assert calls["n"] == 3  # two 429s retried, third succeeded


def test_honors_retry_after_header(monkeypatch):
    slept = []
    _patch_sequence(monkeypatch, [_resp(429, headers={"Retry-After": "0"}), _resp(200, _OK)])
    monkeypatch.setattr(oc.time, "sleep", lambda s: slept.append(s))
    oc.OpenAICompatClient(_cfg()).complete("sys", "user")
    assert slept == [0.0]  # waited exactly the server-specified time


def test_gives_up_after_max_retries(monkeypatch):
    calls = _patch_sequence(monkeypatch, [_resp(429)])  # always rate-limited
    with pytest.raises(LLMError) as ei:
        oc.OpenAICompatClient(_cfg(llm_max_retries=2)).complete("sys", "user")
    assert "429" in str(ei.value)
    assert calls["n"] == 3  # initial + 2 retries, then raises


def test_timeout_maps_to_llmtimeout(monkeypatch):
    _patch_sequence(monkeypatch, [httpx.TimeoutException("slow")])
    with pytest.raises(LLMTimeout):
        oc.OpenAICompatClient(_cfg()).complete("sys", "user")
