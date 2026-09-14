import json
import sys

from medextract import cli

BRIEF_KEYS = {
    "chief_complaint", "symptoms", "diagnosis", "medical_history", "medications",
    "procedures", "follow_up", "summary", "risk_indicators", "urgency", "icd10_codes",
}


def test_cli_writes_json_file(tmp_path, monkeypatch):
    out = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", [
        "medextract.cli",
        "--note", "Cough and fever. Diagnosis pneumonia.",
        "-o", str(out),
    ])
    cli.main()

    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data.keys()) == BRIEF_KEYS
    assert "cough" in [s.lower() for s in data["symptoms"]]


def test_cli_reads_from_file(tmp_path, monkeypatch):
    note = tmp_path / "note.txt"
    note.write_text("Patient denies chest pain. History of asthma.", encoding="utf-8")
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["medextract.cli", "--file", str(note), "-o", str(out)])
    cli.main()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "asthma" in [h.lower() for h in data["medical_history"]]
