"""Stage 3: bounded repair (CLAUDE.md §3.3).

A correction task, not a re-run of extraction. After the attempt limit,
``run_extract_validated`` raises ``ExtractionFailed``; never returns a
partially-guessed object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from ..config import Settings
from ..llm.base import LLMClient
from ..prompts import get_prompt
from ..schemas import ExtractionFailed
from .extract import _SYSTEM, run_extract
from .validate import GroundingReport, StructuralError, ground, parse_structural


@dataclass
class ExtractOutcome:
    grounding: GroundingReport
    repair_attempts: int


def _run_repair(client: LLMClient, previous: str, errors: List[str]) -> str:
    prompt = (
        get_prompt("repair")
        .replace("{errors}", "\n".join(f"- {e}" for e in errors))
        .replace("{previous}", previous)
    )
    return client.complete(_SYSTEM, prompt)


def run_extract_validated(
    note: str, client: LLMClient, cfg: Settings
) -> ExtractOutcome:
    """Extract -> structural validate -> (repair loop) -> evidence grounding."""
    raw = run_extract(note, client, cfg)
    attempts = 0
    last_errors: List[str] = []
    while True:
        try:
            flat = parse_structural(raw)
            break
        except StructuralError as e:
            last_errors = e.details
            if attempts >= cfg.max_repair_attempts:
                raise ExtractionFailed(last_errors) from e
            attempts += 1
            raw = _run_repair(client, raw, last_errors)

    rep = ground(note, flat, cfg.fuzzy_grounding_threshold)
    return ExtractOutcome(grounding=rep, repair_attempts=attempts)
