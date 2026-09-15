"""PRIORITY 5 + 9 - deterministic end-to-end pipeline tests.

Fully offline: the LLM is a ScriptedClient and the ICD-10 agent uses the injected
FakeIcd10Source (conftest autouse fixture) instead of the real online service.
These prove that only VALIDATED, grounded facts reach the summary, risk, and
ICD-10 stages - and that a hallucinated fact removed at grounding cannot resurface
anywhere downstream.
"""

from medextract.brief import to_brief


HAPPY = {
    "chief_complaint": {"text": "chest pain", "evidence": "severe chest pain"},
    "symptoms": [
        {"text": "chest pain", "status": "present", "evidence": "severe chest pain radiating to the left arm"},
        {"text": "shortness of breath", "status": "negated", "evidence": "denies shortness of breath"},
    ],
    "diagnosis": [{"text": "pneumonia", "status": "present", "evidence": "Diagnosis: pneumonia"}],
    "medical_history": [{"text": "hypertension", "status": "historical", "evidence": "history of hypertension"}],
    "medications": [{"name": "aspirin", "dose": "81 mg", "frequency": "daily", "evidence": "aspirin 81 mg daily"}],
    "procedures": [],
    "follow_up": "Follow up in 1 week",
}

NOTE = (
    "Patient with severe chest pain radiating to the left arm. Denies shortness of "
    "breath. History of hypertension. Diagnosis: pneumonia. Taking aspirin 81 mg "
    "daily. Follow up in 1 week."
)


def test_e2e_happy_path(scripted_run):
    resp, _ = scripted_run(NOTE, [HAPPY])

    # extraction + grounding
    assert resp.chief_complaint.text == "chest pain"
    assert any(s.text == "chest pain" and s.status.value == "present" for s in resp.symptoms)
    assert any(h.text == "hypertension" for h in resp.medical_history)
    assert any(m.name == "aspirin" for m in resp.medications)
    assert resp.meta.unsupported_dropped == 0

    # downstream: summary, risk, icd10 all populated from validated data
    assert resp.summary and "chest pain" in resp.summary
    assert resp.urgency == "urgent"  # "severe" + "radiating" in a present span
    coded = {c.source_term.lower(): c.code for c in resp.icd10_codes}
    assert coded.get("pneumonia") == "J18.9"
    assert coded.get("hypertension") == "I10"  # historical is codeable

    # flat brief schema is consistent
    body = to_brief(resp)
    assert "shortness of breath" not in body["symptoms"]  # negated -> dropped from flat


def test_e2e_failure_path_hallucination_contained(scripted_run):
    # The model returns a real supported symptom AND a hallucinated diagnosis
    # whose cited evidence (present in the note) does not support it.
    note = "Patient reports cough and fever."
    out = {
        "symptoms": [{"text": "cough", "status": "present", "evidence": "cough and fever"}],
        "diagnosis": [{"text": "pneumonia", "status": "present", "evidence": "Patient reports cough and fever."}],
    }
    resp, _ = scripted_run(note, [out])

    # 1) grounding removed the unsupported diagnosis
    assert resp.meta.incoherent_dropped >= 1
    assert all(d.text != "pneumonia" for d in resp.diagnosis)

    # 2) it does not appear in the summary
    assert resp.summary is None or "pneumonia" not in resp.summary.lower()

    # 3) it was never sent to the ICD-10 agent
    assert all(c.source_term.lower() != "pneumonia" for c in resp.icd10_codes)

    # 4) the supported fact still flows through
    assert any(s.text == "cough" for s in resp.symptoms)

    # 5) final flat response is grounded (no phantom pneumonia)
    body = to_brief(resp)
    assert "pneumonia" not in [d.lower() for d in body["diagnosis"]]
    assert all(c["diagnosis"].lower() != "pneumonia" for c in body["icd10_codes"])


def test_e2e_include_flags_disable_stages(scripted_run):
    resp, _ = scripted_run(NOTE, [HAPPY], include_icd10=False, include_summary=False)
    assert resp.icd10_codes == []
    assert resp.summary is None
    # risk still runs (it is not gated by a flag)
    assert resp.urgency is not None
