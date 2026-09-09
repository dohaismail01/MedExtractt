"""Schema/guardrail tests — no provider/key required."""
import pytest
from pydantic import ValidationError

from app.schema import Extraction, MedExtractResult, empty_result


def test_empty_result_has_full_shape():
    data = empty_result().model_dump()
    for key in ("chief_complaint", "symptoms", "diagnosis", "medical_history",
                "medications", "procedures", "follow_up", "summary",
                "risk_indicators", "urgency"):
        assert key in data
    assert data["symptoms"] == []
    assert data["chief_complaint"] is None


def test_extra_key_is_rejected():
    with pytest.raises(ValidationError):
        Extraction.model_validate({"chief_complaint": "x", "made_up_field": 1})


def test_invalid_urgency_rejected():
    with pytest.raises(ValidationError):
        MedExtractResult.model_validate({"urgency": "critical"})


def test_valid_urgency_accepted():
    r = MedExtractResult.model_validate({"urgency": "high"})
    assert r.urgency == "high"
