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


def test_api_llm_error_returns_502(monkeypatch):
    from medextract.api import routes
    from medextract.llm.base import LLMError

    def boom(*a, **k):
        raise LLMError("LLM HTTP 400: bad request")

    monkeypatch.setattr(routes, "run", boom)
    r = client.post("/extract", json={"note": "cough and fever"})
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "llm_error"


def test_api_redact():
    r = client.post("/redact", json={"text": "call 555-123-4567"})
    assert r.status_code == 200 and "555-123-4567" not in r.json()["redacted"]


def test_api_include_flags():
    r = client.post("/extract", json={"note": "cough", "include_icd10": False, "include_summary": False})
    body = r.json()
    assert body["icd10_codes"] == [] and body["summary"] is None


# --- PRIORITY 8: API contract edge cases -------------------------------------
def test_api_note_too_large_413():
    big = "cough. " * 20000  # exceeds the 50 KB cap
    r = client.post("/extract", json={"note": big})
    assert r.status_code == 413


def test_api_malformed_request_422():
    # missing required "note" field -> FastAPI/pydantic request validation
    r = client.post("/extract", json={"include_icd10": True})
    assert r.status_code == 422


def test_api_llm_timeout_504(monkeypatch):
    from medextract.api import routes
    from medextract.llm.base import LLMTimeout

    def boom(*a, **k):
        raise LLMTimeout("timed out")

    monkeypatch.setattr(routes, "run", boom)
    r = client.post("/extract", json={"note": "cough and fever"})
    assert r.status_code == 504
    assert r.json()["detail"]["error"] == "llm_timeout"


def test_api_extraction_failed_422(monkeypatch):
    from medextract.api import routes
    from medextract.schemas import ExtractionFailed

    def boom(*a, **k):
        raise ExtractionFailed(["still invalid after repair"])

    monkeypatch.setattr(routes, "run", boom)
    r = client.post("/extract", json={"note": "cough"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "validation_failed" and detail["details"]


def test_api_successful_extraction_200():
    r = client.post("/extract", json={"note": "Cough and fever. Diagnosis pneumonia."})
    assert r.status_code == 200


def test_api_extract_rich_exposes_evidence_and_status():
    r = client.post("/extract/rich", json={"note": NOTE})
    assert r.status_code == 200
    body = r.json()
    # rich response keeps status + grounded evidence offsets (unlike flat /extract)
    sym = body["symptoms"][0]
    assert "status" in sym and "evidence" in sym
    assert sym["evidence"]["text"]
    # ICD-10 suggestions keep confidence + resolution_path
    assert body["icd10_codes"]
    c = body["icd10_codes"][0]
    assert "confidence" in c and "resolution_path" in c and "needs_review" in c
    # evidence offsets, where present, index the original note
    if sym["evidence"]["start"] is not None:
        s, e = sym["evidence"]["start"], sym["evidence"]["end"]
        assert NOTE[s:e].lower() == sym["evidence"]["text"].lower()


def test_api_extract_rich_drops_negated_from_present():
    r = client.post("/extract/rich", json={"note": "Patient denies fever. Reports cough."})
    body = r.json()
    fever = [s for s in body["symptoms"] if s["text"] == "fever"]
    assert fever and fever[0]["status"] == "negated"  # kept, but marked negated


def test_health_works_without_llm(monkeypatch):
    # /health must not invoke the LLM client at all
    from medextract.llm import base

    def fail(*a, **k):
        raise AssertionError("/health must not construct an LLM client")

    monkeypatch.setattr(base, "get_client", fail)
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
