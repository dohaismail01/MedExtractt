"""Map the extraction to HL7 FHIR R4 resources and wrap them in a Bundle.

Honest scope: this is a structural mapping, not a certified FHIR implementation
(no profiles, terminology bindings, or IG validation). It signals domain
awareness and lets the output theoretically enter a real clinical system.

Resources are built as plain dicts conforming to the R4 structure. This keeps
the mapping dependency-light and readable; it can be swapped for `fhir.resources`
model construction later without changing the endpoint contract.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from .schema import MedExtractResult

_ICD10_SYSTEM = "http://hillrom.com/fhir/sid/icd-10-cm"  # display only; see scope note


def _entry(resource: dict) -> dict:
    return {"fullUrl": f"urn:uuid:{uuid.uuid4()}", "resource": resource}


def _condition(text: str, clinical_status: str, icd10: Optional[dict]) -> dict:
    code: dict[str, Any] = {"text": text}
    if icd10 and icd10.get("code"):
        code["coding"] = [
            {"system": _ICD10_SYSTEM, "code": icd10["code"], "display": icd10.get("description", text)}
        ]
    return {
        "resourceType": "Condition",
        "clinicalStatus": {"coding": [{"code": clinical_status}]},
        "code": code,
    }


def _medication_statement(med: dict) -> dict:
    dosage: dict[str, Any] = {}
    if med.get("frequency"):
        dosage["text"] = " ".join(
            p for p in (med.get("dose"), med.get("frequency"), med.get("duration")) if p
        )
    resource: dict[str, Any] = {
        "resourceType": "MedicationStatement",
        "status": "active",
        "medicationCodeableConcept": {"text": med.get("name") or "unspecified"},
    }
    if dosage:
        resource["dosage"] = [dosage]
    return resource


def to_fhir_bundle(result: MedExtractResult, icd10_codes: Optional[dict] = None) -> dict:
    """Serialise a result as a FHIR R4 Bundle of type 'collection'."""
    icd10_codes = icd10_codes or {}
    entries: list[dict] = []

    for dx in result.diagnosis:
        entries.append(_entry(_condition(dx, "active", icd10_codes.get(dx))))

    for hx in result.medical_history:
        entries.append(_entry(_condition(hx, "resolved", None)))

    for med in result.medications:
        entries.append(_entry(_medication_statement(med.model_dump() if hasattr(med, "model_dump") else med)))

    for sym in result.symptoms:
        entries.append(_entry({
            "resourceType": "Observation",
            "status": "final",
            "category": [{"coding": [{"code": "exam"}]}],
            "code": {"text": sym},
        }))

    for proc in result.procedures:
        entries.append(_entry({"resourceType": "Procedure", "status": "completed", "code": {"text": proc}}))

    if result.chief_complaint:
        entries.append(_entry({
            "resourceType": "Encounter",
            "status": "finished",
            "reasonCode": [{"text": result.chief_complaint}],
        }))

    if result.follow_up:
        entries.append(_entry({
            "resourceType": "CarePlan",
            "status": "active",
            "intent": "plan",
            "description": result.follow_up,
        }))

    return {"resourceType": "Bundle", "type": "collection", "entry": entries}
