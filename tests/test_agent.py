"""Agent orchestration (offline). The planner loop and tool model calls are
mocked, so this exercises assembly, verification, and QC confidence with no key."""
import json

import pytest

from app import agent, llm_client


class _Msg:
    content = ""
    tool_calls = None


class _Resp:
    class _C:
        message = _Msg()

    choices = [_C()]


@pytest.fixture(autouse=True)
def _mock_model(monkeypatch):
    # Planner immediately yields no tool calls -> _ensure_complete runs the tools.
    monkeypatch.setattr(llm_client, "create_with_backoff", lambda **k: _Resp())

    def fake_chat(messages, **kw):
        sysmsg = messages[0]["content"].lower()
        if "entities already extracted" in sysmsg:
            return json.dumps({"summary": "s", "risk_indicators": [], "urgency": "low"})
        return json.dumps({
            "chief_complaint": None, "symptoms": ["low mood", "fatigue"],
            "diagnosis": [], "medical_history": [], "medications": [],
            "procedures": [], "follow_up": None,
        })

    monkeypatch.setattr(llm_client, "chat", fake_chat)


def test_agent_assembles_full_payload():
    out = agent.run_agent("Patient feeling low and fatigued.")
    for key in ("symptoms", "summary", "agent_trace", "qc_confidence", "verification"):
        assert key in out
    assert out["symptoms"] == ["low mood", "fatigue"]


def test_agent_trace_is_ordered_and_nonempty():
    out = agent.run_agent("Patient feeling low and fatigued.")
    messages = [t["message"] for t in out["agent_trace"]]
    assert messages[0].startswith("Clinical note received")
    assert any("Verification" in m for m in messages)


def test_grounded_extraction_scores_high_confidence():
    out = agent.run_agent("Patient feeling low and fatigued.")
    assert out["verification"]["grounded"] is True
    assert out["qc_confidence"] >= 75


def test_empty_note_is_handled():
    out = agent.run_agent("   ")
    assert out["symptoms"] == []
    assert "agent_trace" in out
