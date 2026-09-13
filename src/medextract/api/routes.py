"""API routes (CLAUDE.md §5).

POST /extract  -> MedExtractResponse (+ disclaimer)
                  422 validation_failed | 504 llm_timeout
GET  /health   -> { status, model, prompt_version, ... }
POST /redact   -> PHI/PII redaction preview (privacy utility)
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from .. import __version__
from ..brief import to_brief
from ..config import settings
from ..llm.base import LLMTimeout
from ..orchestrator import run
from ..safety import DISCLAIMER, LogSafeNote, NoteValidationError, redact_phi
from ..schemas import MedExtractResponse, ExtractionFailed

logger = logging.getLogger("medextract")
router = APIRouter()


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="invalid or missing API key")


class ExtractRequest(BaseModel):
    note: str = Field(..., description="free-text clinical note")
    include_icd10: bool = True
    include_summary: bool = True


class RedactRequest(BaseModel):
    text: str


@router.get("/health")
def health() -> Dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "model": settings.model,
        "prompt_version": settings.prompt_version,
        "llm_provider": settings.llm_provider,
        "icd10_backend": settings.icd10_backend,
        "auth_required": bool(settings.api_key),
        "redact_input": settings.redact_input,
        "disclaimer": DISCLAIMER,
    }


@router.post("/extract")
def extract(req: ExtractRequest, _: None = Depends(require_api_key)):
    if len(req.note.encode("utf-8")) > settings.max_note_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"note exceeds {settings.max_note_bytes} byte cap",
        )

    safe = LogSafeNote.from_note(req.note)  # never log the raw note
    logger.info("extract len=%d redactions=%s", safe.length, safe.redactions)

    try:
        response: MedExtractResponse = run(
            req.note, include_icd10=req.include_icd10, include_summary=req.include_summary
        )
    except NoteValidationError as e:
        raise HTTPException(status_code=422,
                            detail={"error": "validation_failed", "details": [str(e)]})
    except ExtractionFailed as e:
        raise HTTPException(status_code=422,
                            detail={"error": "validation_failed", "details": e.details})
    except LLMTimeout:
        raise HTTPException(status_code=504, detail={"error": "llm_timeout"})

    # The API returns the assignment's exact flat schema (see medextract/brief.py).
    # The safety disclaimer is surfaced via GET /health and the UI, not inside the
    # extraction body, so the body stays exactly the required schema.
    return to_brief(response)


@router.post("/redact")
def redact(req: RedactRequest, _: None = Depends(require_api_key)) -> Dict[str, object]:
    redacted, counts = redact_phi(req.text)
    return {"redacted": redacted, "redactions": counts}
