"""Grounding-robustness evaluation (PRIORITY 1 / 12).

Measures how well the evidence-grounding layer rejects UNSUPPORTED facts while
keeping SUPPORTED ones. Unlike run_eval (which runs the LLM), this feeds crafted
LLM outputs directly into ``ground()`` so the grounding decision is isolated and
deterministic - no model, no network.

Dataset: ``eval/datasets/grounding_adversarial.jsonl``. Each row is a
``{note, injected, expected}`` triple where ``injected`` is a flat LLM output and
``expected`` is "reject" (the fact is unsupported and must be dropped) or "keep"
(the fact is supported and must survive).

Reported metrics:
  * rejection_rate  - of the facts that SHOULD be rejected, how many were
  * retention_rate  - of the facts that SHOULD be kept, how many were
  * false_accept    - unsupported facts wrongly kept (the dangerous error)
  * false_reject    - supported facts wrongly dropped (a recall cost)

    python -m eval.grounding_eval
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from medextract.config import get_settings  # noqa: E402
from medextract.pipeline.validate import ground  # noqa: E402
from medextract.schemas import LLMExtraction  # noqa: E402

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT / "datasets" / "grounding_adversarial.jsonl"


def _fact_count(result) -> int:
    n = 1 if result.chief_complaint else 0
    for group in (result.symptoms, result.diagnosis, result.medical_history,
                  result.procedures, result.medications):
        n += len(group)
    return n


def evaluate(dataset: Path = DEFAULT) -> Dict:
    cfg = get_settings()
    rows = [json.loads(l) for l in dataset.read_text(encoding="utf-8").splitlines() if l.strip()]

    should_reject = kept_when_reject = 0
    should_keep = kept_when_keep = 0
    failures: List[str] = []

    for row in rows:
        flat = LLMExtraction.model_validate(row["injected"])
        rep = ground(row["note"], flat, cfg.fuzzy_grounding_threshold,
                     min_coverage=cfg.coherence_min_coverage,
                     token_fuzz=cfg.coherence_token_fuzz)
        survived = _fact_count(rep.result) > 0
        if row["expected"] == "reject":
            should_reject += 1
            if survived:
                kept_when_reject += 1
                failures.append(f"{row['id']}: FALSE ACCEPT (unsupported fact kept)")
        else:
            should_keep += 1
            if survived:
                kept_when_keep += 1
            else:
                failures.append(f"{row['id']}: FALSE REJECT (supported fact dropped)")

    return {
        "cases": len(rows),
        "rejection_rate": round((should_reject - kept_when_reject) / max(1, should_reject), 3),
        "retention_rate": round(kept_when_keep / max(1, should_keep), 3),
        "false_accept": kept_when_reject,
        "false_reject": should_keep - kept_when_keep,
        "failures": failures,
    }


def main() -> None:
    report = evaluate()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
