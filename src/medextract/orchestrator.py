"""Wires the full pipeline (SPEC.md §7 / diagram §3).

    note -> validate/redact -> extract -> validate + repair -> validated data
         -> icd10 agent + summary + risk -> MedExtractResponse

Downstream stages read validated structured data only; they never see the raw
note (except risk, which matches its lexicon against validated evidence spans).
"""

from __future__ import annotations

import time
from typing import Optional

from .config import Settings, settings as default_settings
from .icd10.agent import Icd10Agent
from .llm.base import get_client
from .pipeline.repair import run_extract_validated
from .pipeline.risk import assess
from .pipeline.summary import build_summary
from .safety import redact_phi, validate_note
from .schemas import MedExtractResponse, RunMeta


def run(
    note: str,
    cfg: Optional[Settings] = None,
    include_icd10: bool = True,
    include_summary: bool = True,
) -> MedExtractResponse:
    cfg = cfg or default_settings
    t0 = time.perf_counter()

    note = validate_note(note, cfg.max_note_bytes)
    if cfg.redact_input:
        note, _ = redact_phi(note)

    client = get_client(cfg)
    outcome = run_extract_validated(note, client, cfg)  # may raise ExtractionFailed
    result = outcome.grounding.result

    icd10_codes, tool_calls = [], 0
    if include_icd10:
        icd10_codes, tool_calls = Icd10Agent(cfg=cfg).code_result(result)

    summary = build_summary(result) if include_summary else None
    risk_indicators, urgency = assess(result)

    meta = RunMeta(
        prompt_version=cfg.prompt_version,
        model=cfg.model,
        repair_attempts=outcome.repair_attempts,
        unsupported_dropped=outcome.grounding.unsupported_dropped,
        incoherent_dropped=outcome.grounding.incoherent_dropped,
        icd10_tool_calls=tool_calls,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )

    return MedExtractResponse(
        **result.model_dump(),
        summary=summary,
        risk_indicators=risk_indicators,
        urgency=urgency,
        icd10_codes=icd10_codes,
        meta=meta,
    )
