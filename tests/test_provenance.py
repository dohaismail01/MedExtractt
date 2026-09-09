"""Provenance is pure code — testable with no provider/key."""
from app.provenance import build_provenance, hallucination_rate
from app.schema import Extraction


def test_exact_match_is_grounded():
    note = "Patient reports chest pain and nausea."
    ext = Extraction(symptoms=["chest pain", "nausea"])
    prov = build_provenance(note, ext)
    assert all(item["found"] for item in prov["symptoms"])
    assert prov["symptoms"][0]["span"] is not None
    assert hallucination_rate(prov) == 0.0


def test_absent_item_is_ungrounded():
    note = "Patient reports chest pain."
    ext = Extraction(symptoms=["chest pain", "fever"])
    prov = build_provenance(note, ext)
    found = {i["text"]: i["found"] for i in prov["symptoms"]}
    assert found["chest pain"] is True
    assert found["fever"] is False
    assert hallucination_rate(prov) == 0.5


def test_empty_extraction_zero_hallucination():
    prov = build_provenance("anything", Extraction())
    assert hallucination_rate(prov) == 0.0
