"""API contract tests (Plan §10 / test matrix D3-D4, A-series) via TestClient.

The model is mocked, so these run offline with no provider/key and no network.
"""
import pytest
from fastapi.testclient import TestClient

from app import api, config
from app.schema import Medication, MedExtractResult

client = TestClient(api.app)


@pytest.fixture(autouse=True)
def _no_external(monkeypatch):
    # Keep ICD-10 (MCP) and interactions off so no network/subprocess is touched.
    monkeypatch.setattr(config, "ENABLE_ICD10", False)
    monkeypatch.setattr(config, "ENABLE_INTERACTIONS", False)


def _canned(**over):
    base = dict(chief_complaint="cough", symptoms=["cough"], medications=[])
    base.update(over)
    result = MedExtractResult(**base)
    meta = {"version": "final", "attempts": 1, "repaired": False,
            "valid": True, "status": "ok"}
    return result, meta


def test_missing_note_is_422():
    assert client.post("/extract", json={}).status_code == 422


def test_bad_version_is_400():
    r = client.post("/extract?version=nope", json={"note": "x"})
    assert r.status_code == 400


def test_note_too_long_is_413():
    big = "a" * (config.NOTE_MAX_CHARS + 1)
    r = client.post("/extract", json={"note": big})
    assert r.status_code == 413


def test_empty_note_returns_valid_empty_shape():
    r = client.post("/extract", json={"note": "   "})
    assert r.status_code == 200
    body = r.json()
    for key in ("chief_complaint", "symptoms", "diagnosis", "medications",
                "summary", "urgency"):
        assert key in body
    assert body["symptoms"] == []


def test_success_sets_diagnostic_headers(monkeypatch):
    monkeypatch.setattr(api.extract, "extract", lambda note, version="final": _canned())
    r = client.post("/extract", json={"note": "cough note"})
    assert r.status_code == 200
    assert r.headers["X-Validation-Status"] == "ok"
    assert r.headers["X-Repair-Attempts"] == "0"
    assert r.headers["X-Model-Id"]
    assert r.json()["chief_complaint"] == "cough"


def test_provenance_flag_attaches_mapping(monkeypatch):
    monkeypatch.setattr(
        api.extract, "extract",
        lambda note, version="final": _canned(symptoms=["cough"]),
    )
    r = client.post("/extract", json={"note": "patient has cough", "provenance": True})
    body = r.json()
    assert "_provenance" in body
    assert body["_provenance"]["symptoms"][0]["found"] is True


def test_interaction_flags_attached_when_enabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_INTERACTIONS", True)
    monkeypatch.setattr(config, "INTERACTIONS_USE_RXNORM", False)
    monkeypatch.setattr(
        api.extract, "extract",
        lambda note, version="final": _canned(
            medications=[Medication(name="warfarin"), Medication(name="aspirin")]
        ),
    )
    r = client.post("/extract", json={"note": "on warfarin and aspirin"})
    flags = r.json().get("interaction_flags")
    assert flags and set(flags[0]["drugs"]) == {"warfarin", "aspirin"}


def test_fhir_format_returns_bundle(monkeypatch):
    monkeypatch.setattr(
        api.extract, "extract",
        lambda note, version="final": _canned(diagnosis=[]),
    )
    r = client.post("/extract?format=fhir", json={"note": "cough"})
    assert r.status_code == 200
    assert r.json()["resourceType"] == "Bundle"
