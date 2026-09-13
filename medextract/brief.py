"""Assignment-conformant output serializer.

The internal pipeline works with the rich models in ``schemas.py`` (facts carry
``status`` + ``evidence`` offsets, urgency is routine/elevated/urgent, and a
``meta`` block is attached) because evidence grounding is what keeps extraction
closed-world / non-hallucinated. The *API*, however, must return exactly the
flat JSON schema defined in the project brief:

    {
      "chief_complaint": null,          # string
      "symptoms": [],                   # string[]
      "diagnosis": [],                  # string[]
      "medical_history": [],            # string[]
      "medications": [ {name,dose,frequency,duration} ],
      "procedures": [],                 # string[]
      "follow_up": null,                # string
      "summary": null,                  # string
      "risk_indicators": [],            # string[]
      "urgency": null,                  # "low" | "medium" | "high"
      "icd10_codes": [ ... ]            # bonus: diagnosis -> code (or null)
    }

This module is the single place that flattens the rich model to that shape.
Negated and family-history facts are excluded from the affirmative arrays so a
denied or relative's symptom is never listed as one the patient has (the flat
schema has no field to mark status). Missing scalar -> null; missing list -> [].
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schemas import ClinicalFact, MedExtractResponse, Status

# Internal documentation-based urgency -> the brief's low/medium/high vocabulary.
_URGENCY_MAP: Dict[str, str] = {
    "routine": "low",
    "elevated": "medium",
    "urgent": "high",
}

# Facts that represent something the patient affirmatively has / had. Negated and
# family-history facts are dropped from the flat lists (no field to express them).
_AFFIRMATIVE = {Status.PRESENT, Status.HISTORICAL, Status.UNCERTAIN}


def _texts(facts: List[ClinicalFact]) -> List[str]:
    return [f.text for f in facts if f.status in _AFFIRMATIVE]


def to_brief(resp: MedExtractResponse) -> Dict[str, Any]:
    """Flatten a rich ``MedExtractResponse`` to the brief's exact JSON schema."""
    urgency: Optional[str] = _URGENCY_MAP.get(resp.urgency) if resp.urgency else None

    return {
        "chief_complaint": resp.chief_complaint.text if resp.chief_complaint else None,
        "symptoms": _texts(resp.symptoms),
        "diagnosis": _texts(resp.diagnosis),
        "medical_history": [f.text for f in resp.medical_history],
        "medications": [
            {
                "name": m.name,
                "dose": m.dose,
                "frequency": m.frequency,
                "duration": m.duration,
            }
            for m in resp.medications
        ],
        "procedures": _texts(resp.procedures),
        "follow_up": resp.follow_up,
        "summary": resp.summary,
        "risk_indicators": [r.term for r in resp.risk_indicators],
        "urgency": urgency,
        # Bonus (brief §10): map each extracted diagnosis/procedure to a code, or
        # null when the agent could not confidently resolve one.
        "icd10_codes": [
            {
                "diagnosis": c.source_term,
                "code": c.code,
                "description": c.description,
                "confidence": round(c.confidence, 3),
                "needs_review": c.needs_review,
            }
            for c in resp.icd10_codes
        ],
    }
