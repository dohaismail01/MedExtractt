"""Offline evaluation harness (CLAUDE.md §6).

Runs the full pipeline over a JSONL gold set and writes a timestamped JSON +
Markdown report to eval/reports/. Works with whichever provider is configured
(the deterministic stub by default), so the same command measures any prompt or
model.

Usage:
    python -m eval.run_eval
    python -m eval.run_eval --dataset eval/datasets/gold_set.jsonl --prompt-version v2 --limit 100
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

from medextract.config import get_settings  # noqa: E402
from medextract.orchestrator import run  # noqa: E402
from medextract.schemas import Status  # noqa: E402
from eval.metrics import Accumulator  # noqa: E402

ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "datasets" / "gold_set.jsonl"
REPORTS = ROOT / "reports"


def load(path: Path) -> List[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _matches(g: str, preds: set) -> bool:
    return any(g in p or p in g for p in preds)


def evaluate(dataset: Path, prompt_version: str, limit: int | None = None) -> Dict:
    cfg = get_settings().model_copy(update={"prompt_version": prompt_version})
    rows = load(dataset)
    if limit:
        rows = rows[:limit]
    acc = Accumulator()

    for row in rows:
        gold = row.get("gold", {})
        t0 = time.perf_counter()
        resp = run(row["note"], cfg=cfg)
        acc.latencies_ms.append((time.perf_counter() - t0) * 1000)
        acc.notes += 1
        acc.unsupported += resp.meta.unsupported_dropped
        acc.first_pass_valid += 1 if resp.meta.repair_attempts == 0 else 0
        acc.repaired += 1 if resp.meta.repair_attempts > 0 else 0
        acc.tool_calls.append(resp.meta.icd10_tool_calls)

        pred = {s.text.lower() for s in resp.symptoms if s.status == Status.PRESENT}
        pred |= {d.text.lower() for d in resp.diagnosis}
        pred |= {m.name.lower() for m in resp.medications}
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

    return acc.report(prompt_version, cfg.model)


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
