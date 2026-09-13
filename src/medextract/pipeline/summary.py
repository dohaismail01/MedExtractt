"""Stage 5: grounded summary (CLAUDE.md §3.4).

Input: the validated ExtractionResult only - the raw note is NOT passed. Output:
2-4 sentences that introduce no term absent from the structured data (asserted
by a token-overlap test). Deterministic by default; a real LLM summarizer can be
wired via prompts/summary.md without changing this contract.
"""

from __future__ import annotations

from typing import List, Optional

from ..schemas import ExtractionResult, Status


def build_summary(result: ExtractionResult) -> Optional[str]:
    parts: List[str] = []

    if result.chief_complaint:
        parts.append(f"Chief complaint: {result.chief_complaint.text}.")

    present = [s.text for s in result.symptoms if s.status == Status.PRESENT]
    if present:
        parts.append("Reported symptoms: " + ", ".join(present) + ".")

    denied = [s.text for s in result.symptoms if s.status == Status.NEGATED]
    if denied:
        parts.append("Explicitly denied: " + ", ".join(denied) + ".")

    dx = [d.text for d in result.diagnosis]
    if dx:
        parts.append("Documented diagnoses: " + ", ".join(dx) + ".")

    hx = [h.text for h in result.medical_history]
    if hx:
        parts.append("History: " + ", ".join(hx) + ".")

    if result.medications:
        parts.append("Medications: " + ", ".join(m.name for m in result.medications) + ".")

    if result.procedures:
        parts.append("Procedures: " + ", ".join(p.text for p in result.procedures) + ".")

    if result.follow_up:
        parts.append(f"Plan/follow-up: {result.follow_up}")

    # CLAUDE.md §3.4: 2-4 sentences. parts are in priority order; cap the tail.
    return " ".join(parts[:4]) if parts else None
