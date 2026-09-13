import pytest
from pydantic import ValidationError

from medextract.schemas import (
    MedExtractResponse,
    Evidence,
    ExtractionResult,
    ICD10Suggestion,
    RunMeta,
    Status,
)


def test_extraction_defaults():
    r = ExtractionResult()
    assert r.symptoms == []
    assert r.chief_complaint is None
    assert r.follow_up is None


def test_icd10_confidence_bounds():
    with pytest.raises(ValidationError):
        ICD10Suggestion(source_term="x", confidence=1.5, needs_review=True)


def test_response_requires_meta():
    with pytest.raises(ValidationError):
        MedExtractResponse()


def test_response_roundtrip():
    resp = MedExtractResponse(meta=RunMeta(prompt_version="v1", model="stub"))
    d = resp.model_dump()
    assert d["icd10_codes"] == []
    assert d["meta"]["prompt_version"] == "v1"


def test_evidence_offsets_optional():
    e = Evidence(text="chest pain")
    assert e.start is None and e.end is None
