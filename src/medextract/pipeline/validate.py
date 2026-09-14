"""Stage 2: validation (SPEC.md §3.2).

Layer A - structural: parse JSON, coerce through the flat LLM-facing model.
Layer B - evidence grounding, in two steps for each fact:
  1. *Location* - locate the evidence span in the note (exact, then fuzzy via
     rapidfuzz), recording character offsets. Fails -> fact dropped as
     ``unsupported`` (evidence not in note).
  2. *Coherence* - verify the evidence actually SUPPORTS the fact text. Locating
     the span is necessary but NOT sufficient: evidence "Patient reports cough."
     is in the note, but it does not support a diagnosis of "pneumonia". We
     require the fact's content tokens to be covered by the evidence (token
     overlap + fuzzy match). Fails -> fact dropped as ``incoherent``.

Honest limitation: lexical coverage cannot *prove* medical truth. It enforces a
necessary condition (the evidence must mention what is claimed) and
conservatively drops facts that fail it, rather than accepting unsupported
facts. Abbreviation/synonym mismatches (e.g. text "atrial fibrillation" with
evidence "afib") are therefore dropped too - a deliberate false-negative bias.

Structural failures raise ``StructuralError`` (-> repair). Grounding failures do
NOT trigger repair; they are silent quality signals counted in meta.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from pydantic import ValidationError
from rapidfuzz import fuzz

from ..schemas import (
    ClinicalFact,
    Evidence,
    ExtractionResult,
    FlatFact,
    FlatMedication,
    LLMExtraction,
    Medication,
    Status,
)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
_FIRST_OBJ = re.compile(r"\{.*\}", re.S)


class StructuralError(ValueError):
    def __init__(self, details: List[str]):
        self.details = details
        super().__init__("; ".join(details))


@dataclass
class GroundingReport:
    result: ExtractionResult
    unsupported_dropped: int = 0  # total facts dropped (both reasons below)
    incoherent_dropped: int = 0   # subset: evidence found but did not support the fact
    fuzzy_matches: int = 0
    dropped_terms: List[str] = field(default_factory=list)


# --- Layer A ---------------------------------------------------------------
def _find_json(text: str) -> str:
    m = _JSON_FENCE.search(text) or _FIRST_OBJ.search(text)
    if not m:
        raise StructuralError(["no JSON object found in model output"])
    return m.group(1) if m.re is _JSON_FENCE else m.group(0)


def parse_structural(raw: str) -> LLMExtraction:
    try:
        data = json.loads(_find_json(raw))
    except json.JSONDecodeError as e:
        raise StructuralError([f"json: {e}"]) from e
    try:
        return LLMExtraction.model_validate(data)
    except ValidationError as e:
        details = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                   for err in e.errors()]
        raise StructuralError(details) from e


# --- Layer B ---------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


# Function words that carry no clinical content; ignored when measuring whether
# the evidence supports the fact so that "shortness of breath" is judged on
# {shortness, breath}, not on "of".
_COHERENCE_STOP = {
    "a", "an", "the", "of", "to", "for", "with", "without", "and", "or", "in",
    "on", "at", "is", "are", "was", "were", "has", "have", "had", "his", "her",
    "their", "patient", "reports", "report", "reported", "reports", "complains",
    "complaining", "presents", "presenting", "denies", "denied", "history",
    "status", "post", "left", "right", "no", "not", "any", "he", "she", "they",
}


def _content_tokens(s: str) -> List[str]:
    """Content words of a phrase (lowercased, punctuation stripped, function
    words and 1-char tokens removed)."""
    toks = re.findall(r"[a-z0-9]+", s.lower())
    return [t for t in toks if len(t) > 1 and t not in _COHERENCE_STOP]


def _token_supported(token: str, ev_tokens: List[str], token_fuzz: int) -> bool:
    """True if a fact token is present in the evidence tokens: exact, shared
    stem/prefix (radiating~radiate), or a high fuzzy ratio (typo tolerance)."""
    for et in ev_tokens:
        if token == et:
            return True
        # shared 4+ char prefix handles simple morphology (radiating/radiation)
        if len(token) >= 5 and len(et) >= 5 and token[:5] == et[:5]:
            return True
        if fuzz.ratio(token, et) >= token_fuzz:
            return True
    return False


def coherence(fact_text: str, evidence: str, token_fuzz: int = 85) -> float:
    """Fraction of the fact's content tokens that are supported by the evidence.

    1.0 means the evidence mentions everything the fact claims; 0.0 means it
    mentions none of it (e.g. fact "pneumonia" vs evidence "Patient reports
    cough."). A fact with no content tokens of its own falls back to a
    whole-phrase fuzzy containment check against the evidence.
    """
    ft = _content_tokens(fact_text)
    ev_all = re.findall(r"[a-z0-9]+", evidence.lower())
    if not ft:
        # e.g. text is only function words / a single short token: require the
        # normalized text to appear (fuzzily) inside the evidence.
        return 1.0 if fuzz.partial_ratio(_norm(fact_text), _norm(evidence)) >= 90 else 0.0
    hits = sum(1 for t in ft if _token_supported(t, ev_all, token_fuzz))
    return hits / len(ft)


def locate(note: str, span: str) -> Optional[Tuple[int, int]]:
    """Find span in note (case-insensitive, whitespace-flexible). Offsets are in
    the ORIGINAL note index space, or None if not found exactly."""
    if not span:
        return None
    pattern = re.escape(span.strip())
    pattern = re.sub(r"\\?\s+", r"\\s+", pattern)  # flexible whitespace
    m = re.search(pattern, note, re.I)
    return (m.start(), m.end()) if m else None


def _ground_span(note: str, note_norm: str, span: str, fuzzy_threshold: int):
    """Return (Evidence | None, is_fuzzy)."""
    loc = locate(note, span)
    if loc:
        # store the verbatim note substring (SPEC.md §0 rule 2), not the LLM's
        # span, which may differ in case/whitespace after flexible matching.
        return Evidence(text=note[loc[0]:loc[1]], start=loc[0], end=loc[1]), False
    # fuzzy fallback: accepted but no reliable offsets
    if span and fuzz.partial_ratio(_norm(span), note_norm) >= fuzzy_threshold:
        return Evidence(text=span, start=None, end=None), True
    return None, False


def ground(
    note: str,
    flat: LLMExtraction,
    fuzzy_threshold: int = 90,
    min_coverage: float = 0.5,
    token_fuzz: int = 85,
) -> GroundingReport:
    note_norm = _norm(note)
    rep = GroundingReport(result=ExtractionResult(follow_up=flat.follow_up))

    def accept(fact_text: str, evidence: str, label: str):
        """Location (step 1) + coherence (step 2). Returns Evidence or None,
        recording the drop reason. ``evidence`` is the LLM-supplied span; the
        stored Evidence uses the verbatim note substring where located."""
        ev, fuzzy = _ground_span(note, note_norm, evidence, fuzzy_threshold)
        if ev is None:
            rep.unsupported_dropped += 1
            rep.dropped_terms.append(f"{label}:{fact_text}(evidence_not_found)")
            return None
        # step 2: does the (located) evidence actually support the fact?
        if coherence(fact_text, ev.text, token_fuzz) < min_coverage:
            rep.unsupported_dropped += 1
            rep.incoherent_dropped += 1
            rep.dropped_terms.append(f"{label}:{fact_text}(incoherent)")
            return None
        if fuzzy:
            rep.fuzzy_matches += 1
        return ev

    def ground_facts(items: List[FlatFact], label: str) -> List[ClinicalFact]:
        out: List[ClinicalFact] = []
        for f in items:
            ev = accept(f.text, f.evidence, label)
            if ev is not None:
                out.append(ClinicalFact(text=f.text, status=f.status, evidence=ev))
        return out

    # chief complaint
    if flat.chief_complaint:
        ev = accept(flat.chief_complaint.text, flat.chief_complaint.evidence, "chief_complaint")
        if ev is not None:
            rep.result.chief_complaint = ClinicalFact(
                text=flat.chief_complaint.text, status=Status.PRESENT, evidence=ev
            )

    rep.result.symptoms = ground_facts(flat.symptoms, "symptom")
    rep.result.diagnosis = ground_facts(flat.diagnosis, "diagnosis")
    rep.result.medical_history = ground_facts(flat.medical_history, "history")
    rep.result.procedures = ground_facts(flat.procedures, "procedure")

    meds: List[Medication] = []
    for m in flat.medications:
        # medications are grounded on the drug NAME (the fact being asserted).
        ev = accept(m.name, m.evidence, "medication")
        if ev is not None:
            meds.append(Medication(name=m.name, dose=m.dose, frequency=m.frequency,
                                   duration=m.duration, evidence=ev))
    rep.result.medications = meds
    return rep
