"""PRIORITY 3 - high-value adversarial regression tests.

These use a scripted LLM (see conftest.ScriptedClient / scripted_run) so the
exact model output - including hallucinations and unsupported facts - is under
test control. Each asserts the pipeline REMOVES what the note does not support.
"""


def _diag(text, evidence, status="present"):
    return {"diagnosis": [{"text": text, "status": status, "evidence": evidence}]}


def _terms(facts):
    return {f.text.lower() for f in facts}


def test_hallucinated_diagnosis_with_present_evidence_removed(scripted_run):
    # Note says headache; model invents migraine but cites the headache sentence.
    note = "Patient reports headache."
    resp, _ = scripted_run(note, [_diag("migraine", "Patient reports headache.")])
    assert "migraine" not in _terms(resp.diagnosis)
    assert resp.meta.incoherent_dropped >= 1


def test_wrong_evidence_diagnosis_removed(scripted_run):
    note = "Patient reports headache."
    resp, _ = scripted_run(note, [_diag("diabetes", "Patient reports headache.")])
    assert "diabetes" not in _terms(resp.diagnosis)


def test_negation_detected(scripted_run):
    note = "Patient denies chest pain."
    out = {"symptoms": [{"text": "chest pain", "status": "negated",
                         "evidence": "Patient denies chest pain"}]}
    resp, _ = scripted_run(note, [out])
    assert any(s.text == "chest pain" and s.status.value == "negated"
               for s in resp.symptoms)


def test_historical_detected(scripted_run):
    note = "Past medical history includes asthma."
    out = {"medical_history": [{"text": "asthma", "status": "historical",
                               "evidence": "Past medical history includes asthma"}]}
    resp, _ = scripted_run(note, [out])
    assert any(h.text == "asthma" and h.status.value == "historical"
               for h in resp.medical_history)


def test_family_history_detected(scripted_run):
    note = "Father had diabetes."
    out = {"medical_history": [{"text": "diabetes", "status": "family_history",
                               "evidence": "Father had diabetes"}]}
    resp, _ = scripted_run(note, [out])
    assert any(h.text == "diabetes" and h.status.value == "family_history"
               for h in resp.medical_history)


def test_uncertainty_detected(scripted_run):
    note = "Possible pneumonia."
    resp, _ = scripted_run(note, [_diag("pneumonia", "Possible pneumonia", "uncertain")])
    assert any(d.text == "pneumonia" and d.status.value == "uncertain"
               for d in resp.diagnosis)


def test_unsupported_medication_removed(scripted_run):
    # Note has no medication; model invents aspirin with an unrelated evidence span.
    note = "Patient reports headache."
    out = {"medications": [{"name": "aspirin", "dose": "81 mg",
                           "evidence": "Patient reports headache."}]}
    resp, _ = scripted_run(note, [out])
    assert resp.medications == []
    assert resp.meta.incoherent_dropped >= 1


def test_unsupported_medication_fabricated_evidence_removed(scripted_run):
    # Model fabricates an evidence span that is not in the note at all.
    note = "Patient reports headache."
    out = {"medications": [{"name": "aspirin", "evidence": "aspirin 81 mg daily"}]}
    resp, _ = scripted_run(note, [out])
    assert resp.medications == []


def test_unsupported_procedure_removed(scripted_run):
    # Note has no ECG; model invents one citing the headache sentence.
    note = "Patient reports headache."
    out = {"procedures": [{"text": "ECG", "status": "present",
                          "evidence": "Patient reports headache."}]}
    resp, _ = scripted_run(note, [out])
    assert "ecg" not in _terms(resp.procedures)


def test_procedure_with_real_evidence_kept(scripted_run):
    note = "ECG ordered in clinic."
    out = {"procedures": [{"text": "ECG", "status": "present", "evidence": "ECG ordered"}]}
    resp, _ = scripted_run(note, [out])
    assert "ecg" in _terms(resp.procedures)
