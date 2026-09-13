import pytest
from fastapi.testclient import TestClient

from medextract.api.app import create_app
from medextract.config import get_settings
from medextract.orchestrator import run
from medextract.safety import NoteValidationError
from medextract.schemas import Status

client = TestClient(create_app())

NOTE = (
    "Chief complaint: chest pain. Patient presents with severe chest pain radiating "
    "to the left arm. Denies shortness of breath. History of hypertension. Taking "
    "amlodipine 5 mg daily. Diagnosis: acute myocardial infarction. Follow up in 1 week."
)


def test_orchestrator_end_to_end():
    resp = run(NOTE)
    assert any(s.text == "chest pain" and s.status == Status.PRESENT for s in resp.symptoms)
    assert any(h.text == "hypertension" for h in resp.medical_history)
    codes = {c.source_term.lower(): c.code for c in resp.icd10_codes}
    assert codes.get("myocardial infarction") == "I21.9"
    assert codes.get("hypertension") == "I10"
    assert resp.urgency == "urgent"
    assert resp.summary and "chest pain" in resp.summary
    assert resp.meta.model == get_settings().model
    assert resp.meta.icd10_tool_calls >= 1


def test_orchestrator_offsets_are_valid():
    resp = run(NOTE)
    for s in resp.symptoms:
        if s.evidence.start is not None:
            assert NOTE[s.evidence.start:s.evidence.end].lower() == s.evidence.text.lower()


def test_orchestrator_validation_error():
    with pytest.raises(NoteValidationError):
        run("   ")


def test_api_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "prompt_version" in body and "model" in body
    assert body["disclaimer"]  # safety disclaimer surfaced here, not in /extract


BRIEF_KEYS = {
    "chief_complaint", "symptoms", "diagnosis", "medical_history", "medications",
    "procedures", "follow_up", "summary", "risk_indicators", "urgency", "icd10_codes",
}


def test_api_extract_returns_exact_brief_schema():
    r = client.post("/extract", json={"note": "Cough and fever. Diagnosis pneumonia."})
    assert r.status_code == 200
    body = r.json()
    # exactly the brief's flat schema: no evidence / status / meta / disclaimer
    assert set(body.keys()) == BRIEF_KEYS
    assert body["symptoms"] == [s for s in body["symptoms"] if isinstance(s, str)]
    assert all(isinstance(s, str) for s in body["symptoms"])
    assert "cough" in [s.lower() for s in body["symptoms"]]
    codes = {c["diagnosis"].lower(): c["code"] for c in body["icd10_codes"]}
    assert codes.get("pneumonia") == "J18.9"


def test_api_extract_urgency_vocabulary():
    r = client.post("/extract", json={
        "note": "Patient reports severe chest pain radiating to the left arm.",
    })
    body = r.json()
    assert body["urgency"] in {"low", "medium", "high", None}
    assert body["urgency"] == "high"
    assert all(isinstance(t, str) for t in body["risk_indicators"])


def test_api_empty_note_422():
    r = client.post("/extract", json={"note": "   "})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "validation_failed"


def test_api_redact():
    r = client.post("/redact", json={"text": "call 555-123-4567"})
    assert r.status_code == 200 and "555-123-4567" not in r.json()["redacted"]


def test_api_include_flags():
    r = client.post("/extract", json={"note": "cough", "include_icd10": False, "include_summary": False})
    body = r.json()
    assert body["icd10_codes"] == [] and body["summary"] is None
