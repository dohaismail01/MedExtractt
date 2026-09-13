import pytest

from medextract.safety import (
    NoteValidationError,
    contains_phi,
    redact_phi,
    validate_note,
)


def test_validate_rejects_empty():
    with pytest.raises(NoteValidationError):
        validate_note("   ", 1000)


def test_validate_rejects_oversized():
    with pytest.raises(NoteValidationError):
        validate_note("x" * 100, 10)


def test_validate_ok():
    assert validate_note("cough", 100) == "cough"


def test_redact_ssn_phone_email():
    red, counts = redact_phi("SSN 123-45-6789, call 555-123-4567, email jane@doe.com")
    assert "123-45-6789" not in red and "jane@doe.com" not in red
    assert counts.get("SSN") == 1 and counts.get("EMAIL") == 1 and counts.get("PHONE") == 1


def test_redact_preserves_clinical_content():
    red, _ = redact_phi("Patient: John Doe MRN: A12345 presents with cough")
    assert "A12345" not in red and "John Doe" not in red
    assert "cough" in red


def test_contains_phi():
    assert contains_phi("dob 01/02/1990") is True
    assert contains_phi("patient reports cough and fever") is False
