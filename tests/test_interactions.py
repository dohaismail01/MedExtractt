"""Drug interaction flags (§12.3). Offline: name-match path, no RxNorm calls."""
from app.interactions import STATUS, check_interactions


def test_known_pair_is_flagged():
    flags = check_interactions(["warfarin", "aspirin"], use_rxnorm=False)
    assert len(flags) == 1
    assert set(flags[0]["drugs"]) == {"warfarin", "aspirin"}
    assert flags[0]["source"] == "ONCHigh"
    assert flags[0]["status"] == STATUS


def test_unrelated_pair_not_flagged():
    assert check_interactions(["amoxicillin", "acetaminophen"], use_rxnorm=False) == []


def test_single_medication_returns_empty():
    assert check_interactions(["warfarin"], use_rxnorm=False) == []


def test_order_independent_and_deduplicated():
    a = check_interactions(["aspirin", "warfarin"], use_rxnorm=False)
    assert len(a) == 1  # same pair regardless of order, counted once


def test_multiple_pairs_among_three_drugs():
    # warfarin+aspirin and warfarin+fluconazole are both on the list.
    flags = check_interactions(["warfarin", "aspirin", "fluconazole"], use_rxnorm=False)
    pairs = {frozenset(f["drugs"]) for f in flags}
    assert frozenset({"warfarin", "aspirin"}) in pairs
    assert frozenset({"warfarin", "fluconazole"}) in pairs


def test_status_never_stronger_than_flagging():
    # The status text must not assert clinical significance.
    for f in check_interactions(["simvastatin", "clarithromycin"], use_rxnorm=False):
        assert f["status"] == "flagged for pharmacist review"
