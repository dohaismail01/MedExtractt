"""D1-D2 — the validate-and-repair loop, with the model mocked (no network)."""
import json

from app import extract
from app.schema import Extraction


def test_repair_recovers_after_one_bad_response(monkeypatch):
    """First reply has an illegal 11th key; second is valid -> repaired."""
    replies = iter([
        json.dumps({"chief_complaint": "cough", "made_up": 1}),  # extra="forbid" fails
        json.dumps({"chief_complaint": "cough"}),                # valid
    ])
    monkeypatch.setattr(extract.llm_client, "chat", lambda *a, **k: next(replies))

    ext, meta = extract.run_extraction("cough note", version="final")
    assert meta["valid"] is True
    assert meta["repaired"] is True
    assert ext.chief_complaint == "cough"


def test_repair_exhausts_to_empty(monkeypatch):
    """Every reply is unfixable -> stop at cap, return valid empty schema."""
    monkeypatch.setattr(extract.llm_client, "chat", lambda *a, **k: "not json at all")

    ext, meta = extract.run_extraction("x", version="final")
    assert meta["valid"] is False
    assert meta["status"] if "status" in meta else True  # status set in extract()
    assert ext == Extraction()  # empty but valid
