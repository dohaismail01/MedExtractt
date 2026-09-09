"""Provenance: locate each extracted item in the source note and return spans
(Plan §12.1).

Computed in code, never by the model — LLMs are unreliable at character
counting, so asking for offsets yields confident wrong numbers. This makes the
hallucination metric a hard check: an item that cannot be located, OR that sits
inside a negation scope, is ungrounded by construction (`found: false`).

Grounding is judged against the NOTE, never the gold set.
"""
from __future__ import annotations

from .normalise import find_grounded_span
from .schema import Extraction

_STRING_LIST_FIELDS = ("symptoms", "diagnosis", "medical_history", "procedures")
_SCALAR_FIELDS = ("chief_complaint", "follow_up")


def _locate(note: str, text) -> dict:
    if not text:
        return {"text": text, "span": None, "found": False}
    span = find_grounded_span(note, text)
    return {"text": text, "span": span, "found": span is not None}


def build_provenance(note: str, extraction: Extraction) -> dict:
    """Return a `_provenance` mapping: field -> list of {text, span, found}."""
    prov: dict[str, list[dict]] = {}

    for field in _STRING_LIST_FIELDS:
        prov[field] = [_locate(note, item) for item in getattr(extraction, field)]

    for field in _SCALAR_FIELDS:
        value = getattr(extraction, field)
        if value:
            prov[field] = [_locate(note, value)]

    prov["medications"] = [
        _locate(note, med.name) for med in extraction.medications if med.name
    ]

    return prov


def hallucination_rate(provenance: dict) -> float:
    """count(found == false) / count(all items). 0.0 when there are no items."""
    total = ungrounded = 0
    for items in provenance.values():
        for item in items:
            total += 1
            if not item["found"]:
                ungrounded += 1
    return ungrounded / total if total else 0.0
