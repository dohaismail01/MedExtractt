"""PRIORITY 1 - evidence grounding must enforce fact<->evidence *support*.

Locating the evidence span in the note is necessary but NOT sufficient: the
evidence must actually mention what the fact claims. These tests cover the 12
required cases, including the adversarial one where the evidence exists in the
note but does not support the extracted fact.
"""

from medextract.pipeline.validate import coherence, ground
from medextract.schemas import LLMExtraction, Status


def _ground_one(note, *, kind="diagnosis", text="x", status="present", evidence=""):
    if kind == "chief_complaint":
        payload = {"chief_complaint": {"text": text, "evidence": evidence}}
    elif kind == "medications":
        payload = {"medications": [{"name": text, "evidence": evidence}]}
    else:
        payload = {kind: [{"text": text, "status": status, "evidence": evidence}]}
    return ground(note, LLMExtraction.model_validate(payload))


def _items(rep, kind):
    return getattr(rep.result, kind)


# 1. valid fact + valid evidence -> accepted
def test_valid_fact_valid_evidence_accepted():
    rep = _ground_one("Patient has severe chest pain.", kind="symptoms",
                      text="chest pain", evidence="severe chest pain")
    assert len(rep.result.symptoms) == 1
    assert rep.unsupported_dropped == 0 and rep.incoherent_dropped == 0


# 2. fact text not present anywhere in the note (evidence also absent) -> rejected
def test_fact_not_in_note_rejected():
    rep = _ground_one("Patient reports cough.", kind="symptoms",
                      text="seizure", evidence="patient had a seizure")
    assert rep.result.symptoms == []
    assert rep.unsupported_dropped == 1 and rep.incoherent_dropped == 0  # evidence_not_found


# 3. evidence string not in note -> rejected (location step)
def test_evidence_not_in_note_rejected():
    rep = _ground_one("Patient reports cough.", kind="diagnosis",
                      text="pneumonia", evidence="chest x-ray shows pneumonia")
    assert rep.result.diagnosis == []
    assert rep.unsupported_dropped == 1


# 4. fact and evidence unrelated (both real, evidence in note) -> rejected
def test_fact_and_evidence_unrelated_rejected():
    rep = _ground_one("Patient reports cough. Blood pressure normal.",
                      kind="diagnosis", text="hypertension",
                      evidence="Blood pressure normal.")
    assert rep.result.diagnosis == []
    assert rep.incoherent_dropped == 1


# 5. hallucinated diagnosis with unrelated but present evidence -> rejected
#    (THE adversarial case from the brief)
def test_adversarial_hallucination_rejected():
    note = "Patient reports cough."
    rep = _ground_one(note, kind="diagnosis", text="pneumonia",
                      evidence="Patient reports cough.")
    assert rep.result.diagnosis == []
    assert rep.incoherent_dropped == 1
    assert any("incoherent" in t for t in rep.dropped_terms)


# 6. negated fact - status preserved, coherence still enforced on the term
def test_negated_fact_accepted_with_status():
    rep = _ground_one("Patient denies fever.", kind="symptoms",
                      text="fever", status="negated", evidence="denies fever")
    assert len(rep.result.symptoms) == 1
    assert rep.result.symptoms[0].status == Status.NEGATED


# 7. historical fact
def test_historical_fact_accepted():
    rep = _ground_one("History of hypertension.", kind="medical_history",
                      text="hypertension", status="historical",
                      evidence="History of hypertension")
    assert len(rep.result.medical_history) == 1
    assert rep.result.medical_history[0].status == Status.HISTORICAL


# 8. family-history fact
def test_family_history_fact_accepted():
    rep = _ground_one("Mother has a history of stroke.", kind="medical_history",
                      text="stroke", status="family_history",
                      evidence="Mother has a history of stroke")
    assert len(rep.result.medical_history) == 1
    assert rep.result.medical_history[0].status == Status.FAMILY_HISTORY


# 9. uncertain fact
def test_uncertain_fact_accepted():
    rep = _ground_one("Possible pneumonia.", kind="diagnosis",
                      text="pneumonia", status="uncertain", evidence="Possible pneumonia")
    assert len(rep.result.diagnosis) == 1
    assert rep.result.diagnosis[0].status == Status.UNCERTAIN


# 10. fuzzy evidence matching (typo in evidence) still grounds + stays coherent
def test_fuzzy_evidence_matching():
    note = "Patient with severe chest pain."
    rep = _ground_one(note, kind="symptoms", text="chest pain",
                      evidence="sevre chest pain")  # typo -> fuzzy path
    assert len(rep.result.symptoms) == 1
    assert rep.fuzzy_matches == 1


# 11. empty evidence -> rejected
def test_empty_evidence_rejected():
    rep = _ground_one("Patient reports cough.", kind="symptoms",
                      text="cough", evidence="")
    assert rep.result.symptoms == []
    assert rep.unsupported_dropped == 1


# 12. evidence containing only generic words -> rejected (no support for the term)
def test_generic_only_evidence_rejected():
    note = "The patient has been seen in the clinic today."
    rep = _ground_one(note, kind="diagnosis", text="pneumonia",
                      evidence="The patient has been seen")
    assert rep.result.diagnosis == []
    assert rep.incoherent_dropped == 1


# --- coherence() unit checks --------------------------------------------------
def test_coherence_scoring():
    assert coherence("pneumonia", "Patient reports cough.") == 0.0
    assert coherence("chest pain", "severe chest pain radiating") == 1.0
    assert coherence("shortness of breath", "denies shortness of breath") == 1.0
    # partial multi-word support is allowed above the default 0.5 coverage
    assert coherence("pain radiating to the left arm", "radiating to the left arm") >= 0.5


def test_medication_grounded_on_name():
    note = "Started aspirin 81 mg daily."
    rep = _ground_one(note, kind="medications", text="aspirin",
                      evidence="aspirin 81 mg daily")
    assert len(rep.result.medications) == 1
    # a medication whose evidence does not mention the drug is dropped
    rep2 = _ground_one("Patient reports cough.", kind="medications",
                       text="aspirin", evidence="Patient reports cough.")
    assert rep2.result.medications == []
    assert rep2.incoherent_dropped == 1
