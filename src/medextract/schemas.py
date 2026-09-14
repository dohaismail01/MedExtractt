"""Data contracts (SPEC.md §2). Pydantic v2.

These models are the interface between every stage - no dicts cross module
boundaries. The LLM is asked for a *flatter* shape (evidence as a plain
string); ``pipeline/validate.py`` lifts that into ``Evidence`` with offsets.
Keep the LLM-facing schema simple; keep the internal schema strict.

Conventions: missing scalar -> null; missing list -> []. Never omit a key.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Status(str, Enum):
    PRESENT = "present"
    NEGATED = "negated"
    HISTORICAL = "historical"
    FAMILY_HISTORY = "family_history"
    UNCERTAIN = "uncertain"


Urgency = Literal["routine", "elevated", "urgent"]
CodeSystem = Literal["ICD-10-CM", "ICD-10-PCS"]


# ---------------------------------------------------------------------------
# Internal (strict) models
# ---------------------------------------------------------------------------
class Evidence(BaseModel):
    text: str  # verbatim span from the note
    start: Optional[int] = None  # filled by the validator, not the LLM
    end: Optional[int] = None


class ClinicalFact(BaseModel):
    text: str
    status: Status = Status.PRESENT
    evidence: Evidence


class Medication(BaseModel):
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    evidence: Evidence


class ICD10Suggestion(BaseModel):
    source_term: str  # the validated diagnosis/procedure text
    code: Optional[str] = None  # None when confidence insufficient
    description: Optional[str] = None
    code_system: Optional[CodeSystem] = None
    confidence: float = Field(ge=0.0, le=1.0)
    needs_review: bool
    resolution_path: List[str] = Field(default_factory=list)  # audit trail


class RiskIndicator(BaseModel):
    term: str  # e.g. "severe", "radiating"
    evidence: Evidence


class ExtractionResult(BaseModel):
    chief_complaint: Optional[ClinicalFact] = None
    symptoms: List[ClinicalFact] = Field(default_factory=list)
    diagnosis: List[ClinicalFact] = Field(default_factory=list)
    medical_history: List[ClinicalFact] = Field(default_factory=list)
    medications: List[Medication] = Field(default_factory=list)
    procedures: List[ClinicalFact] = Field(default_factory=list)
    follow_up: Optional[str] = None


class RunMeta(BaseModel):
    prompt_version: str
    model: str
    repair_attempts: int = 0
    unsupported_dropped: int = 0
    incoherent_dropped: int = 0  # subset of unsupported: evidence found but did not support the fact
    icd10_tool_calls: int = 0
    latency_ms: int = 0


class MedExtractResponse(ExtractionResult):
    summary: Optional[str] = None
    risk_indicators: List[RiskIndicator] = Field(default_factory=list)
    urgency: Optional[Urgency] = None
    icd10_codes: List[ICD10Suggestion] = Field(default_factory=list)
    meta: RunMeta


# ---------------------------------------------------------------------------
# LLM-facing (flat) models: evidence is a plain string. The extractor produces
# this; the validator lifts it into the strict models above.
# ---------------------------------------------------------------------------
class FlatFact(BaseModel):
    text: str
    status: Status = Status.PRESENT
    evidence: str


class FlatMedication(BaseModel):
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    evidence: str


class FlatCC(BaseModel):
    text: str
    evidence: str


class LLMExtraction(BaseModel):
    chief_complaint: Optional[FlatCC] = None
    symptoms: List[FlatFact] = Field(default_factory=list)
    diagnosis: List[FlatFact] = Field(default_factory=list)
    medical_history: List[FlatFact] = Field(default_factory=list)
    medications: List[FlatMedication] = Field(default_factory=list)
    procedures: List[FlatFact] = Field(default_factory=list)
    follow_up: Optional[str] = None


class ExtractionFailed(Exception):
    """Raised when extraction cannot produce a valid object within the repair budget."""

    def __init__(self, details: List[str]):
        self.details = details
        super().__init__("; ".join(details) if details else "extraction failed")
