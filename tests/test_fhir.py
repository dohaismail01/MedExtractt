"""FHIR R4 Bundle mapping (§12.2). Pure function, no provider/key."""
from app.fhir_export import to_fhir_bundle
from app.schema import Medication, MedExtractResult


def _sample() -> MedExtractResult:
    return MedExtractResult(
        chief_complaint="chest pain",
        symptoms=["chest pain", "diaphoresis"],
        diagnosis=["unstable angina"],
        medical_history=["hypertension"],
        medications=[Medication(name="aspirin", dose="325mg")],
        procedures=["electrocardiogram"],
        follow_up="cardiology in 1 week",
        summary="Patient with chest pain.",
        risk_indicators=["chest pain"],
        urgency="high",
    )


def test_bundle_shape():
    bundle = to_fhir_bundle(_sample())
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert isinstance(bundle["entry"], list) and bundle["entry"]


def test_resource_types_present():
    bundle = to_fhir_bundle(_sample())
    types = {e["resource"]["resourceType"] for e in bundle["entry"]}
    assert {"Condition", "MedicationStatement", "Observation", "Procedure",
            "Encounter", "CarePlan"} <= types


def test_diagnosis_condition_carries_icd10_when_supplied():
    bundle = to_fhir_bundle(_sample(), icd10_codes={"unstable angina": {"code": "I20.0"}})
    conditions = [
        e["resource"] for e in bundle["entry"]
        if e["resource"]["resourceType"] == "Condition"
    ]
    active = [c for c in conditions if c["clinicalStatus"]["coding"][0]["code"] == "active"]
    assert any(
        c.get("code", {}).get("coding", [{}])[0].get("code") == "I20.0" for c in active
    )


def test_history_is_resolved_condition():
    bundle = to_fhir_bundle(_sample())
    conditions = [
        e["resource"] for e in bundle["entry"]
        if e["resource"]["resourceType"] == "Condition"
    ]
    assert any(c["clinicalStatus"]["coding"][0]["code"] == "resolved" for c in conditions)


def test_empty_result_yields_empty_bundle():
    bundle = to_fhir_bundle(MedExtractResult())
    assert bundle["resourceType"] == "Bundle"
    assert bundle["entry"] == []
