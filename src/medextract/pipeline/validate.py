"""Stage 2: validation (SPEC.md §3.2).

Layer A - structural: parse JSON, coerce through the flat LLM-facing model.
Layer B - evidence grounding: locate each span in the note, record offsets,
drop facts whose evidence cannot be found (fuzzy fallback via rapidfuzz).

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
    unsupported_dropped: int = 0
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


def ground(note: str, flat: LLMExtraction, fuzzy_threshold: int = 90) -> GroundingReport:
    note_norm = _norm(note)
    rep = GroundingReport(result=ExtractionResult(follow_up=flat.follow_up))

    def ground_facts(items: List[FlatFact], label: str) -> List[ClinicalFact]:
        out: List[ClinicalFact] = []
        for f in items:
            ev, fuzzy = _ground_span(note, note_norm, f.evidence, fuzzy_threshold)
            if ev is None:
                rep.unsupported_dropped += 1
                rep.dropped_terms.append(f"{label}:{f.text}")
                continue
            if fuzzy:
                rep.fuzzy_matches += 1
            out.append(ClinicalFact(text=f.text, status=f.status, evidence=ev))
        return out

    # chief complaint
    if flat.chief_complaint:
        ev, fuzzy = _ground_span(note, note_norm, flat.chief_complaint.evidence, fuzzy_threshold)
        if ev is not None:
            if fuzzy:
                rep.fuzzy_matches += 1
            rep.result.chief_complaint = ClinicalFact(
                text=flat.chief_complaint.text, status=Status.PRESENT, evidence=ev
            )
        else:
            rep.unsupported_dropped += 1
            rep.dropped_terms.append("chief_complaint")

    rep.result.symptoms = ground_facts(flat.symptoms, "symptom")
    rep.result.diagnosis = ground_facts(flat.diagnosis, "diagnosis")
    rep.result.medical_history = ground_facts(flat.medical_history, "history")
    rep.result.procedures = ground_facts(flat.procedures, "procedure")

    meds: List[Medication] = []
    for m in flat.medications:
        ev, fuzzy = _ground_span(note, note_norm, m.evidence, fuzzy_threshold)
        if ev is None:
            rep.unsupported_dropped += 1
            rep.dropped_terms.append(f"medication:{m.name}")
            continue
        if fuzzy:
            rep.fuzzy_matches += 1
        meds.append(Medication(name=m.name, dose=m.dose, frequency=m.frequency,
                               duration=m.duration, evidence=ev))
    rep.result.medications = meds
    return rep
