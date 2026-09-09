"""§7.3 / C4 — negation-aware grounding. No provider/key required."""
from app.normalise import in_negation_scope
from app.provenance import build_provenance
from app.schema import Extraction


def test_denies_is_negated():
    note = "Patient denies chest pain."
    idx = note.lower().find("chest pain")
    assert in_negation_scope(note, idx) is True


def test_plain_finding_not_negated():
    note = "Patient reports chest pain."
    idx = note.lower().find("chest pain")
    assert in_negation_scope(note, idx) is False


def test_boundary_stops_scope():
    # The comma boundary means "chest pain" is not under the earlier "no".
    note = "no fever, has chest pain"
    idx = note.lower().find("chest pain")
    assert in_negation_scope(note, idx) is False


def test_negated_symptom_counts_as_ungrounded():
    note = "Patient denies chest pain."
    ext = Extraction(symptoms=["chest pain"])
    prov = build_provenance(note, ext)
    # Present as substring but negated -> not grounded.
    assert prov["symptoms"][0]["found"] is False
