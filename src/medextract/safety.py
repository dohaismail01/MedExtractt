"""Safety, privacy, and input-validation utilities (SPEC.md §0 rule 6, §5).

Pragmatic prototype controls, not certified de-identification or security:
  * privacy    -- best-effort PHI/PII redaction + a detector, so raw notes are
                  never logged at INFO or above.
  * validation -- reject empty / oversized input with clear errors.
  * safety     -- a clinician-facing disclaimer attached to output.

Regex redaction does NOT catch free-text names without a labelled field and is
not HIPAA Safe Harbor compliant. Do not soften that limitation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

DISCLAIMER = "Suggestions for clinician review. Not a diagnostic or triage tool."


class NoteValidationError(ValueError):
    """Raised when an input note fails validation."""


def validate_note(note: str, max_bytes: int) -> str:
    if note is None or not str(note).strip():
        raise NoteValidationError("note is empty")
    n = str(note)
    if len(n.encode("utf-8")) > max_bytes:
        raise NoteValidationError(f"note exceeds max size ({max_bytes} bytes)")
    return n


_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("MRN", re.compile(r"\b(?:MRN|medical record(?: number)?)\s*[:#]?\s*[A-Za-z0-9-]+", re.I)),
    ("DATE", re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")),
    ("DATE", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    ("NAME", re.compile(r"\b(?:patient name|name|patient)\s*[:#]\s*[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,3}", re.I)),
    ("NAME", re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Miss)\.?\s+[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)?")),
]


def redact_phi(text: str) -> Tuple[str, Dict[str, int]]:
    if not text:
        return text, {}
    counts: Dict[str, int] = {}
    out = text
    for label, pat in _PATTERNS:
        def _sub(m, _label=label):
            counts[_label] = counts.get(_label, 0) + 1
            return f"[REDACTED-{_label}]"
        out = pat.sub(_sub, out)
    return out, counts


def contains_phi(text: str) -> bool:
    _, counts = redact_phi(text)
    return bool(counts)


@dataclass
class LogSafeNote:
    length: int
    redactions: Dict[str, int]
    preview: str

    @classmethod
    def from_note(cls, note: str) -> "LogSafeNote":
        redacted, counts = redact_phi(note or "")
        return cls(length=len(note or ""), redactions=counts, preview=redacted[:80])
