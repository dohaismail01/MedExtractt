"""Stage 5: documentation-based risk flags + urgency (CLAUDE.md §3.5).

Deterministic, no LLM. A curated lexicon (shipped as data/risk_lexicon.json) of
intensity/acuity terms is matched against the evidence spans of status==present
facts. Urgency derives from an auditable rule table. This is NOT triage - it
reflects language present in the note.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..schemas import Evidence, ExtractionResult, RiskIndicator, Status, Urgency

_LEXICON_PATH = Path(__file__).resolve().parent.parent / "data" / "risk_lexicon.json"


@lru_cache
def _lexicon() -> Dict[str, List[str]]:
    return json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))

# Rule table: urgency as a function of matched-category counts. Auditable.
def _urgency_rule(high: int, moderate: int, has_content: bool) -> Optional[Urgency]:
    if high >= 1:
        return "urgent"
    if moderate >= 1:
        return "elevated"
    return "routine" if has_content else None


def _present_spans(result: ExtractionResult) -> List[Evidence]:
    spans: List[Evidence] = []
    if result.chief_complaint and result.chief_complaint.status == Status.PRESENT:
        spans.append(result.chief_complaint.evidence)
    for group in (result.symptoms, result.diagnosis, result.procedures):
        spans.extend(f.evidence for f in group if f.status == Status.PRESENT)
    return spans


def assess(result: ExtractionResult) -> Tuple[List[RiskIndicator], Optional[Urgency]]:
    lex = _lexicon()
    spans = _present_spans(result)
    indicators: List[RiskIndicator] = []
    seen = set()
    high = moderate = 0

    for category, terms in (("high_acuity", lex["high_acuity"]),
                            ("moderate", lex["moderate"])):
        for span in spans:
            low = span.text.lower()
            for term in terms:
                if term in low and term not in seen:
                    seen.add(term)
                    # offset the term within the note using the span's base offset
                    start = end = None
                    if span.start is not None:
                        idx = low.index(term)
                        start = span.start + idx
                        end = start + len(term)
                    indicators.append(
                        RiskIndicator(term=term, evidence=Evidence(text=term, start=start, end=end))
                    )
                    if category == "high_acuity":
                        high += 1
                    else:
                        moderate += 1

    has_content = bool(
        result.chief_complaint or result.symptoms or result.diagnosis
        or result.medical_history or result.medications or result.procedures
    )
    return indicators, _urgency_rule(high, moderate, has_content)
