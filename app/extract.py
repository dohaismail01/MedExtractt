"""The extraction pipeline (Plan §5.3–5.4).

    Clinical Note -> Prompt -> LLM -> JSON -> Validation (+repair)
                  -> Summary / Risk Flags -> Final Response

Two model calls:
  Call 1  extraction fields, from the note.
  Call 2  summary / risk / urgency, from the VALIDATED JSON ONLY (not the note),
          which makes it structurally unable to introduce new facts.
Call 3 (ICD-10) is layered on in api.py so this stays free of network tool calls.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import ValidationError

from . import config, llm_client
from .schema import Assessment, Extraction, MedExtractResult


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    """Load and cache a prompt file by stem (e.g. 'final', 'narrative', 'repair')."""
    return (config.PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


def _format_validation_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"- {loc}: {err['msg']}")
    return "\n".join(lines)


def _call_with_repair(messages: list[dict], schema, max_tokens: int) -> tuple[Optional[object], int]:
    """Generate → validate → repair loop. Returns (validated_obj|None, attempts).

    On failure the specific error is fed back via repair.txt so the model fixes
    that exact problem. Returns None when REPAIR_MAX_ATTEMPTS is exhausted.
    """
    convo = list(messages)
    for attempt in range(config.REPAIR_MAX_ATTEMPTS + 1):
        raw = llm_client.chat(convo, json_mode=True, max_tokens=max_tokens)
        data = llm_client.parse_json(raw)
        if data is not None:
            try:
                return schema.model_validate(data), attempt + 1
            except ValidationError as exc:
                errors = _format_validation_error(exc)
        else:
            errors = "Response was not valid JSON. Return a single JSON object."

        if attempt == config.REPAIR_MAX_ATTEMPTS:
            return None, attempt + 1
        convo = convo + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": load_prompt("repair").format(errors=errors)},
        ]
    return None, config.REPAIR_MAX_ATTEMPTS + 1


def run_extraction(note: str, version: str = config.DEFAULT_VERSION) -> tuple[Extraction, dict]:
    """Call 1 + validation/repair loop.

    Returns the validated Extraction and metadata: attempts, whether repair
    fired, and validity. When repair is exhausted the empty (but valid)
    extraction is returned rather than raising.
    """
    system = load_prompt(version)
    user = f"<note>\n{note}\n</note>"
    obj, attempts = _call_with_repair(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        Extraction,
        config.MAX_TOKENS_CALL1,
    )
    meta = {
        "version": version,
        "attempts": attempts,
        "repaired": obj is not None and attempts > 1,
        "valid": obj is not None,
    }
    return (obj or Extraction()), meta


def run_assessment(extraction: Extraction) -> Assessment:
    """Call 2. The validated JSON goes in; the raw note does NOT."""
    system = load_prompt("narrative")
    obj, _ = _call_with_repair(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": extraction.model_dump_json(indent=2)},
        ],
        Assessment,
        config.MAX_TOKENS_CALL2,
    )
    return obj or Assessment()


def extract(note: str, version: str = config.DEFAULT_VERSION) -> tuple[MedExtractResult, dict]:
    """Full two-call pipeline. Returns the 10-field result and pipeline metadata.

    Metadata carries `status` in {ok, repaired, exhausted} for the
    X-Validation-Status header.
    """
    if not note or not note.strip():
        return MedExtractResult(), {
            "version": version, "attempts": 0, "valid": True,
            "empty_input": True, "status": "ok",
        }

    extraction, meta = run_extraction(note, version)
    assessment = run_assessment(extraction) if meta["valid"] else Assessment()

    meta["status"] = "ok" if meta["valid"] and not meta["repaired"] else (
        "repaired" if meta["valid"] else "exhausted"
    )
    result = MedExtractResult(**extraction.model_dump(), **assessment.model_dump())
    return result, meta
