# MedExtract — Manual Test Cases

A test case documents the inputs, preconditions, and **expected result** used to
validate a specific aspect of the system. The table below is a manual/acceptance
checklist for MedExtract; the automated equivalents live in `tests/` (run with
`python -m pytest`). ICD-10 coding is online-only (NLM), so TC09/TC10 require
internet; everything else is deterministic offline.

| ID | Test case | Example input | Expected result |
|----|-----------|---------------|-----------------|
| **TC01** | Basic extraction | `Patient reports cough and fever for 3 days. History of asthma. Currently taking salbutamol.` | Extracts **cough, fever**, **asthma** as medical history, and **salbutamol** as medication. |
| **TC02** | Unsupported fact rejection | `Patient reports cough and fever. No diagnosis is documented.` | If the LLM incorrectly extracts **pneumonia**, grounding rejects it because pneumonia is not supported by the note. |
| **TC03** | Incoherent / mis-attributed evidence | `Patient denies diabetes. His mother has a history of diabetes.` | Diabetes must **not** appear as the patient's positive diagnosis. "Patient denies diabetes" → **negated**; "mother has a history of diabetes" → **family_history**. Positive diagnosis list is empty. |
| **TC04** | Negation handling | `Patient denies chest pain, shortness of breath, and dizziness.` | Chest pain, shortness of breath, and dizziness are **not** treated as present symptoms (kept as negated). |
| **TC05** | Medication extraction | `Patient is taking amoxicillin 500 mg twice daily for 7 days.` | Medication: **amoxicillin**; dose: **500 mg**; frequency: **twice daily**; duration: **7 days**. |
| **TC06** | Missing information | `Patient presents with headache.` | `symptoms` contains headache; unavailable fields remain **null/empty** rather than invented. |
| **TC07** | Structural repair | `Patient has cough and fever.` | If the LLM returns an invalid structure (e.g. `"symptoms": "cough"` instead of a list), the system triggers repair and validates the corrected response. |
| **TC08** | Risk / urgency | `Patient presents with severe abdominal pain and acute vomiting.` | Configured risk indicators are detected and the deterministic urgency logic produces the appropriate urgency level. |
| **TC09** | ICD-10 abstention | `Patient reports an unusual symptom with no clear documented diagnosis.` | The ICD-10 agent does **not** invent a diagnosis/code; it abstains / marks the result for review when it cannot confidently resolve a code. |
| **TC10** | Full end-to-end | `Patient presents with severe cough and fever for 3 days. History of asthma. Currently taking salbutamol. Follow-up in one week.` | Complete response contains structured extraction, grounded evidence, summary, risk/urgency, ICD-10 candidates where applicable, and metadata. |

## Where each is covered automatically

| TC | Automated coverage (in `tests/`) |
|----|----------------------------------|
| TC01, TC06 | `test_orchestrator_api.py`, `test_status.py` |
| TC02 | `test_grounding_coherence.py`, `test_adversarial.py` |
| TC03 | `test_status.py` (`test_*_not_a_positive_diagnosis`, `test_combined_*`), `test_grounding_coherence.py` |
| TC04 | `test_status.py`, `test_adversarial.py` |
| TC05 | `test_adversarial.py` (medication cases), mocked-LLM cases in `test_orchestrator_api.py` |
| TC07 | `test_repair.py` |
| TC08 | `test_risk_summary.py` |
| TC09 | `test_icd10.py` (abstention / never-invents cases) |
| TC10 | `test_e2e.py` |

## Notes

- **TC03 behavior (fixed):** a negated or family-history condition is preserved
  with its status + evidence in the rich/audit output, but is excluded from the
  patient's positive diagnosis/symptom lists (flat API and the UI's affirmative
  sections). Negated findings appear under a separate "Denied / ruled out" view;
  family history appears under "Medical history".
- **Extraction is the LLM's job.** TC03/TC04 classification quality depends on the
  configured model; the deterministic guarantees are grounding, output shaping,
  and status handling — which is what the automated tests pin down.
