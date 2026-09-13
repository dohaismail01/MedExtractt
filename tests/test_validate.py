import pytest

from medextract.pipeline.validate import (
    StructuralError,
    ground,
    locate,
    parse_structural,
)
from medextract.schemas import LLMExtraction, Status

NOTE = "Patient presents with severe chest pain. Denies shortness of breath. Taking amlodipine 5 mg daily."


def test_parse_structural_ok():
    raw = '{"symptoms": [{"text": "chest pain", "status": "present", "evidence": "severe chest pain"}]}'
    flat = parse_structural(raw)
    assert isinstance(flat, LLMExtraction)
    assert flat.symptoms[0].text == "chest pain"


def test_parse_structural_from_fence():
    raw = '```json\n{"follow_up": "return in 1 week"}\n```'
    assert parse_structural(raw).follow_up == "return in 1 week"


def test_parse_structural_bad_json():
    with pytest.raises(StructuralError):
        parse_structural("not json at all")


def test_parse_structural_bad_status():
    raw = '{"symptoms": [{"text": "x", "status": "bogus", "evidence": "x"}]}'
    with pytest.raises(StructuralError) as ei:
        parse_structural(raw)
    assert ei.value.details  # compact error list populated


def test_locate_offsets():
    start, end = locate(NOTE, "chest pain")
    assert NOTE[start:end].lower() == "chest pain"


def test_locate_whitespace_flexible():
    assert locate("severe   chest\npain here", "chest pain") is not None


def test_ground_populates_offsets_and_status():
    flat = LLMExtraction.model_validate({
        "symptoms": [
            {"text": "chest pain", "status": "present", "evidence": "severe chest pain"},
            {"text": "shortness of breath", "status": "negated", "evidence": "Denies shortness of breath"},
        ],
    })
    rep = ground(NOTE, flat)
    assert rep.unsupported_dropped == 0
    s0 = rep.result.symptoms[0]
    assert s0.evidence.start is not None
    assert NOTE[s0.evidence.start:s0.evidence.end].lower() == "severe chest pain"


def test_ground_drops_unsupported():
    flat = LLMExtraction.model_validate({
        "symptoms": [{"text": "seizure", "status": "present", "evidence": "patient had a seizure"}],
    })
    rep = ground(NOTE, flat)
    assert rep.unsupported_dropped == 1
    assert rep.result.symptoms == []
    assert rep.dropped_terms == ["symptom:seizure"]


def test_ground_fuzzy_match_counts():
    # near-miss evidence (typo) accepted via fuzzy, offsets None
    flat = LLMExtraction.model_validate({
        "symptoms": [{"text": "chest pain", "status": "present", "evidence": "sevre chest pain"}],
    })
    rep = ground(NOTE, flat, fuzzy_threshold=85)
    assert rep.fuzzy_matches == 1
    assert rep.result.symptoms[0].evidence.start is None
