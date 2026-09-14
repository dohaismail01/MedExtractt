"""Offline evaluation harness (SPEC.md §6).

Runs the full pipeline over a JSONL gold set and writes a timestamped JSON +
Markdown report to eval/reports/. Works with whichever provider is configured
(the deterministic stub by default), so the same command measures any prompt or
model.

The eval set is the real HuggingFace ``chenhaodev/medical-dialogs-notes`` clinical
notes (no synthetic/generated data). Generate it first with
``python -m eval.prepare_hf_dataset``. Those notes carry no gold labels, so the
harness reports the label-free metrics (schema validity, unsupported-extraction
rate, repair rate, ICD-10 abstention, latency); P/R/F1 are shown only if a
dataset provides ``gold`` labels.

Usage:
    python -m eval.prepare_hf_dataset            # build the eval set first
    python -m eval.run_eval
    python -m eval.run_eval --dataset eval/datasets/medical_dialogs_notes.jsonl --prompt-version v2 --limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from medextract.brief import to_brief  # noqa: E402
from medextract.config import get_settings  # noqa: E402
from medextract.orchestrator import run  # noqa: E402
from medextract.schemas import Status  # noqa: E402
from eval.metrics import Accumulator  # noqa: E402

ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "datasets" / "medical_dialogs_notes.jsonl"
REPORTS = ROOT / "reports"


def load(path: Path) -> List[dict]:
    if not path.exists():
        raise SystemExit(
            f"dataset not found: {path}\n"
            "Generate the eval set first:  python -m eval.prepare_hf_dataset"
        )
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _matches(g: str, preds: set) -> bool:
    return any(g in p or p in g for p in preds)


def run_version(
    dataset: Path, prompt_version: str, limit: int | None = None
) -> tuple[Dict, List[dict]]:
    """Run the pipeline for one prompt version over the dataset.

    Returns ``(report, outputs)`` where ``outputs`` is the per-note record
    (note, flat JSON output, and run meta) so each prompt version's output can be
    saved and inspected, not just its aggregate metrics.
    """
    cfg = get_settings().model_copy(update={"prompt_version": prompt_version})
    rows = load(dataset)
    if limit:
        rows = rows[:limit]
    acc = Accumulator()
    outputs: List[dict] = []

    for row in rows:
        gold = row.get("gold", {})
        t0 = time.perf_counter()
        resp = run(row["note"], cfg=cfg)
        latency = (time.perf_counter() - t0) * 1000
        acc.latencies_ms.append(latency)
        acc.notes += 1
        acc.unsupported += resp.meta.unsupported_dropped
        acc.first_pass_valid += 1 if resp.meta.repair_attempts == 0 else 0
        acc.repaired += 1 if resp.meta.repair_attempts > 0 else 0
        acc.tool_calls.append(resp.meta.icd10_tool_calls)

        outputs.append({
            "note": row["note"],
            "output": to_brief(resp),
            "repair_attempts": resp.meta.repair_attempts,
            "unsupported_dropped": resp.meta.unsupported_dropped,
            "latency_ms": round(latency, 1),
        })

        pred = {s.text.lower() for s in resp.symptoms if s.status == Status.PRESENT}
        pred |= {d.text.lower() for d in resp.diagnosis}
        pred |= {m.name.lower() for m in resp.medications}
        acc.pred_facts += len(pred)  # counted for every note, gold or not
        # P/R/F1 only where the note carries gold labels; gold-less notes (e.g.
        # the HF dialogue-notes set) still contribute the label-free metrics.
        if gold:
            goldset = set()
            for key in ("symptoms_present", "diagnosis", "diagnosis_uncertain",
                        "medical_history", "medications"):
                goldset |= {t.lower() for t in gold.get(key, [])}
            matched_g = {g for g in goldset if _matches(g, pred)}
            matched_p = {p for p in pred if _matches(p, goldset)}
            acc.tp += len(matched_g)
            acc.fn += len(goldset - matched_g)
            acc.fp += len(pred - matched_p)

        gold_icd = gold.get("icd10", {})
        pred_icd = {c.source_term.lower(): c for c in resp.icd10_codes}
        for term, code in gold_icd.items():
            acc.icd_total += 1
            c = pred_icd.get(term.lower())
            if c is None or c.code is None:
                acc.icd_abstain += 1
            elif c.code.upper() == code.upper():
                acc.icd_tp += 1

        if "urgency" in gold:
            acc.urg_total += 1
            if resp.urgency == gold["urgency"]:
                acc.urg_correct += 1

    return acc.report(prompt_version, cfg.model), outputs


def evaluate(dataset: Path, prompt_version: str, limit: int | None = None) -> Dict:
    report, _ = run_version(dataset, prompt_version, limit)
    return report


def write_reports(report: Dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (REPORTS / f"eval_{ts}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = ["# Eval report", "", f"- generated: {ts}",
          f"- prompt_version: {report['prompt_version']}",
          f"- model: {report['model']}", f"- notes: {report['notes']}", "",
          "| metric | value |", "|---|---|"]
    for k, v in report.items():
        if k in ("prompt_version", "model", "notes"):
            continue
        md.append(f"| {k} | {v} |")
    md_path = REPORTS / f"eval_{ts}.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return md_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(DEFAULT_DATASET))
    ap.add_argument("--prompt-version", default=get_settings().prompt_version)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    report = evaluate(Path(args.dataset), args.prompt_version, args.limit)
    print(json.dumps(report, indent=2))
    md = write_reports(report)
    print(f"\nreports written to {md.parent}")


if __name__ == "__main__":
    main()
