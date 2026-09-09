"""Pydantic models (Plan §1.4). The response model *is* the schema — one
definition serves validation, the API contract, and the auto-generated /docs.

`extra="forbid"` turns an invented 11th key from the model into a validation
error rather than a silent pass. Splitting the extraction block from the
narrative block means a Call 2 failure cannot invalidate a good Call 1 result.

Extension keys (icd10_codes, _provenance) are NOT model fields — they are
attached to the serialised dict at response assembly, so strict validation
always runs against the mandated 10-field contract.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Urgency = Literal["low", "medium", "high"]
STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Medication(BaseModel):
    """One prescribed/administered medication. Fields absent from the note are null."""

    model_config = STRICT

    name: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None


class Extraction(BaseModel):
    """Call 1 output — the 7 fields explicitly present in the note."""

    model_config = STRICT

    chief_complaint: Optional[str] = None
    symptoms: list[str] = Field(default_factory=list)
    diagnosis: list[str] = Field(default_factory=list)
    medical_history: list[str] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    procedures: list[str] = Field(default_factory=list)
    follow_up: Optional[str] = None


class Assessment(BaseModel):
    """Call 2 output — 3 fields derived only from the validated extraction."""

    model_config = STRICT

    summary: Optional[str] = None
    risk_indicators: list[str] = Field(default_factory=list)
    urgency: Optional[Urgency] = None


class MedExtractResult(BaseModel):
    """The public contract — exactly 10 fields, in this order, on every response."""

    model_config = STRICT

    chief_complaint: Optional[str] = None
    symptoms: list[str] = Field(default_factory=list)
    diagnosis: list[str] = Field(default_factory=list)
    medical_history: list[str] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    procedures: list[str] = Field(default_factory=list)
    follow_up: Optional[str] = None
    summary: Optional[str] = None
    risk_indicators: list[str] = Field(default_factory=list)
    urgency: Optional[Urgency] = None


def empty_result() -> "MedExtractResult":
    """The valid empty schema, returned when the repair loop is exhausted.

    The contract is 'always the same shape' — consumers keep working and the
    failure surfaces in evaluation (and the X-Validation-Status header) rather
    than being hidden.
    """
    return MedExtractResult()
