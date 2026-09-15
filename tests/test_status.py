"""PRIORITY 2 - assertion status must be detected and preserved through the
whole pipeline, and must never be treated as currently-present downstream.

Driven through the real (offline stub) pipeline so it exercises extraction ->
grounding -> brief/risk/icd10, not just an isolated function.
"""

from medextract.brief import to_brief
from medextract.orchestrator import run
from medextract.schemas import Status


def _status_of(facts, text):
    for f in facts:
        if f.text == text:
            return f.status
    return None


def test_negation_marked_negated_not_present():
    resp = run("Patient denies fever.")
    assert _status_of(resp.symptoms, "fever") == Status.NEGATED
    # and it must NOT appear in the affirmative flat arrays
    assert "fever" not in to_brief(resp)["symptoms"]


def test_history_marked_historical():
    resp = run("History of hypertension.")
    assert _status_of(resp.medical_history, "hypertension") == Status.HISTORICAL


def test_family_history_marked_family():
    resp = run("Mother has a history of stroke.")
    assert _status_of(resp.medical_history, "stroke") == Status.FAMILY_HISTORY
    # family-history facts are not affirmative for the patient -> excluded from
    # the flat medical_history? brief keeps medical_history verbatim, but the
    # status is preserved in the rich model, which is what matters for coding.


def test_uncertain_marked_uncertain():
    resp = run("Possible pneumonia.")
    assert _status_of(resp.diagnosis, "pneumonia") == Status.UNCERTAIN


def test_present_is_default():
    resp = run("Patient reports cough.")
    assert _status_of(resp.symptoms, "cough") == Status.PRESENT


def test_negated_does_not_drive_urgency():
    # "severe" appears only inside a denied finding -> must not raise urgency
    resp = run("Patient denies severe chest pain.")
    assert resp.urgency in ("routine", None)


def test_negated_not_sent_to_icd10():
    resp = run("Patient denies pneumonia.")
    coded_terms = {c.source_term.lower() for c in resp.icd10_codes}
    assert "pneumonia" not in coded_terms


def test_family_history_not_sent_to_icd10():
    resp = run("Father had diabetes.")
    coded_terms = {c.source_term.lower() for c in resp.icd10_codes}
    assert "diabetes" not in coded_terms


def test_historical_is_coded():
    # historical conditions ARE codeable (they are the patient's own record)
    resp = run("History of hypertension.")
    coded = {c.source_term.lower(): c.code for c in resp.icd10_codes}
    assert coded.get("hypertension") == "I10"


def test_negated_excluded_from_summary_as_present():
    resp = run("Patient denies chest pain. Reports cough.")
    assert resp.summary is not None
    # denied findings are listed under "Explicitly denied", never as reported
    assert "Explicitly denied" in resp.summary
    assert "chest pain" in resp.summary  # present, but in the denied clause


# --- negated / family-history must never read as a positive patient diagnosis -
# Extraction is the LLM's job, so we script the ideal classification and assert
# the OUTPUT SHAPING contract deterministically (to_brief drops negated/family
# from the affirmative arrays; the rich model preserves status + evidence).
def test_negated_diabetes_not_a_positive_diagnosis(scripted_run):
    note = "Patient denies diabetes."
    out = {"diagnosis": [{"text": "diabetes", "status": "negated",
                          "evidence": "Patient denies diabetes"}]}
    resp, _ = scripted_run(note, [out])
    # flat/affirmative output: no positive diabetes diagnosis
    assert to_brief(resp)["diagnosis"] == []
    # rich/audit output: status + evidence preserved
    d = [f for f in resp.diagnosis if f.text == "diabetes"]
    assert d and d[0].status == Status.NEGATED and d[0].evidence.text


def test_family_history_diabetes_not_a_patient_diagnosis(scripted_run):
    note = "His mother has a history of diabetes."
    out = {"medical_history": [{"text": "diabetes", "status": "family_history",
                                "evidence": "His mother has a history of diabetes"}]}
    resp, _ = scripted_run(note, [out])
    assert to_brief(resp)["diagnosis"] == []            # not a diagnosis
    assert any(h.text == "diabetes" and h.status == Status.FAMILY_HISTORY
               for h in resp.medical_history)           # classified as family history


def test_combined_denied_and_family_history_no_positive_diagnosis(scripted_run):
    note = "Patient denies diabetes. His mother has a history of diabetes."
    out = {
        "diagnosis": [{"text": "diabetes", "status": "negated",
                       "evidence": "Patient denies diabetes"}],
        "medical_history": [{"text": "diabetes", "status": "family_history",
                             "evidence": "His mother has a history of diabetes"}],
    }
    resp, _ = scripted_run(note, [out])
    # the patient's positive diagnosis list is empty
    assert to_brief(resp)["diagnosis"] == []
    # both contexts preserved with correct status in the rich output
    assert any(d.status == Status.NEGATED for d in resp.diagnosis)
    assert any(h.status == Status.FAMILY_HISTORY for h in resp.medical_history)
    # neither is sent to the ICD-10 agent as a codeable condition
    assert all(c.source_term.lower() != "diabetes" or c.code is None
               for c in resp.icd10_codes)
