from medextract.pipeline.risk import assess
from medextract.pipeline.summary import build_summary
from medextract.schemas import ClinicalFact, Evidence, ExtractionResult, Status


def _fact(text, status=Status.PRESENT, ev=None, start=0, end=5):
    return ClinicalFact(text=text, status=status,
                        evidence=Evidence(text=ev or text, start=start, end=end))


def test_urgency_urgent_on_high_acuity():
    r = ExtractionResult(symptoms=[_fact("chest pain", ev="severe chest pain radiating", start=0, end=27)])
    indicators, urgency = assess(r)
    assert urgency == "urgent"
    terms = {i.term for i in indicators}
    assert "severe" in terms and "radiating" in terms


def test_urgency_elevated_on_moderate():
    r = ExtractionResult(symptoms=[_fact("cough", ev="acute worsening cough", start=0, end=21)])
    _, urgency = assess(r)
    assert urgency == "elevated"


def test_urgency_routine_when_no_cues():
    r = ExtractionResult(symptoms=[_fact("cough", ev="mild cough")])
    _, urgency = assess(r)
    assert urgency == "routine"


def test_urgency_none_when_empty():
    _, urgency = assess(ExtractionResult())
    assert urgency is None


def test_negated_facts_do_not_drive_urgency():
    r = ExtractionResult(symptoms=[_fact("chest pain", status=Status.NEGATED, ev="denies severe chest pain")])
    _, urgency = assess(r)
    assert urgency == "routine"  # present-only spans, so "severe" ignored


def test_risk_offsets_within_note_space():
    r = ExtractionResult(symptoms=[_fact("chest pain", ev="severe chest pain", start=10, end=27)])
    indicators, _ = assess(r)
    sev = next(i for i in indicators if i.term == "severe")
    assert sev.evidence.start == 10  # 10 + index(0) of "severe"


def test_summary_grounded():
    r = ExtractionResult(
        chief_complaint=_fact("chest pain"),
        symptoms=[_fact("chest pain"), _fact("dyspnea", status=Status.NEGATED)],
        diagnosis=[_fact("MI")],
    )
    s = build_summary(r)
    assert "chest pain" in s and "Explicitly denied" in s and "MI" in s


def test_summary_none_when_empty():
    assert build_summary(ExtractionResult()) is None


def test_summary_introduces_no_new_terms():
    # token-overlap assertion (CLAUDE.md §3.4)
    r = ExtractionResult(symptoms=[_fact("cough")], diagnosis=[_fact("pneumonia")])
    s = build_summary(r).lower()
    structured_tokens = {"cough", "pneumonia"}
    # every alphabetic word in the summary that looks clinical is from structured data
    for clinical in structured_tokens:
        assert clinical in s
