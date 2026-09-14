import pytest

from medextract.config import get_settings
from medextract.pipeline.repair import run_extract_validated
from medextract.schemas import ExtractionFailed

NOTE = "Patient with cough and fever. Diagnosis pneumonia."


class ScriptedClient:
    """Returns a scripted sequence of outputs; used to drive the repair loop."""

    name = "scripted"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def complete(self, system, user):
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return out


def test_first_pass_valid_no_repair():
    cfg = get_settings()
    good = '{"symptoms": [{"text": "cough", "status": "present", "evidence": "cough and fever"}]}'
    out = run_extract_validated(NOTE, ScriptedClient([good]), cfg)
    assert out.repair_attempts == 0
    assert out.grounding.result.symptoms[0].text == "cough"


def test_repair_then_success():
    cfg = get_settings()
    bad = "not json"
    good = '{"symptoms": [{"text": "fever", "status": "present", "evidence": "cough and fever"}]}'
    client = ScriptedClient([bad, good])
    out = run_extract_validated(NOTE, client, cfg)
    assert out.repair_attempts == 1
    assert out.grounding.result.symptoms[0].text == "fever"


def test_invalid_schema_triggers_repair():
    cfg = get_settings()
    bad = '{"symptoms": [{"text": "cough", "status": "bogus_status", "evidence": "cough"}]}'
    good = '{"symptoms": [{"text": "cough", "status": "present", "evidence": "cough and fever"}]}'
    client = ScriptedClient([bad, good])
    out = run_extract_validated(NOTE, client, cfg)
    assert out.repair_attempts == 1  # the enum error triggered exactly one repair


def test_exhausted_raises_extraction_failed():
    cfg = get_settings().model_copy(update={"max_repair_attempts": 2})
    client = ScriptedClient(["bad", "still bad", "nope", "never valid"])
    with pytest.raises(ExtractionFailed) as ei:
        run_extract_validated(NOTE, client, cfg)
    assert ei.value.details
    assert client.calls == 3  # 1 initial + 2 repairs


def test_max_repair_attempts_respected():
    for limit in (0, 1, 3):
        cfg = get_settings().model_copy(update={"max_repair_attempts": limit})
        client = ScriptedClient(["bad"] * (limit + 5))
        with pytest.raises(ExtractionFailed):
            run_extract_validated(NOTE, client, cfg)
        assert client.calls == limit + 1  # 1 initial + `limit` repairs, no more


def test_no_partial_object_after_exhaustion():
    cfg = get_settings().model_copy(update={"max_repair_attempts": 1})
    client = ScriptedClient(["bad", "still bad"])
    result = None
    with pytest.raises(ExtractionFailed):
        result = run_extract_validated(NOTE, client, cfg)
    assert result is None  # nothing (not even a partial guess) is returned


def test_repair_does_not_bypass_evidence_grounding():
    # The repair returns structurally-valid JSON, but with a hallucinated fact
    # whose evidence does not support it. Grounding must still drop it: repair
    # fixes structure, it does not grant a pass on grounding.
    cfg = get_settings()
    bad = "not json"
    repaired = ('{"diagnosis": [{"text": "pneumonia", "status": "present", '
                '"evidence": "Diagnosis pneumonia"}, '
                '{"text": "cancer", "status": "present", "evidence": "with cough and fever"}]}')
    out = run_extract_validated(NOTE, ScriptedClient([bad, repaired]), cfg)
    assert out.repair_attempts == 1
    dx = {d.text for d in out.grounding.result.diagnosis}
    assert "pneumonia" in dx            # supported -> kept
    assert "cancer" not in dx           # unsupported invention -> dropped
    assert out.grounding.incoherent_dropped >= 1


def test_repair_does_not_invent_missing_information():
    # A repair that returns an empty-but-valid object must NOT be back-filled
    # with guessed facts; we get exactly what the (repaired) model returned.
    cfg = get_settings()
    out = run_extract_validated(NOTE, ScriptedClient(["oops", "{}"]), cfg)
    assert out.repair_attempts == 1
    r = out.grounding.result
    assert r.symptoms == [] and r.diagnosis == [] and r.medications == []
