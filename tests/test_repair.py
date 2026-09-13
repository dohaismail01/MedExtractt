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


def test_exhausted_raises_extraction_failed():
    cfg = get_settings().model_copy(update={"max_repair_attempts": 2})
    client = ScriptedClient(["bad", "still bad", "nope", "never valid"])
    with pytest.raises(ExtractionFailed) as ei:
        run_extract_validated(NOTE, client, cfg)
    assert ei.value.details
    assert client.calls == 3  # 1 initial + 2 repairs
