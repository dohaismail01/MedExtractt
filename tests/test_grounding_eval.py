"""Regression guard for the grounding-robustness harness (PRIORITY 1 / 12).

Locks in that the crafted adversarial set is fully rejected and the supported
set fully retained, so a future change that weakens grounding is caught here.
Fully offline (no LLM, no network).
"""

from eval.grounding_eval import evaluate


def test_grounding_robustness_perfect_on_curated_set():
    report = evaluate()
    assert report["cases"] >= 16
    assert report["false_accept"] == 0, report["failures"]   # no unsupported fact kept
    assert report["false_reject"] == 0, report["failures"]   # no supported fact dropped
    assert report["rejection_rate"] == 1.0
    assert report["retention_rate"] == 1.0
