"""Prompt-iteration comparison harness (project brief §7, SPEC.md §6).

Runs the pipeline for each prompt version (V1 -> V2 -> V3 -> Final) over the same
dataset and, for each version:

  * saves every note's output to ``eval/reports/prompt_runs/<version>.jsonl``
    (so the output of each prompt is kept, not just aggregate numbers), and
  * records aggregate metrics.

It then writes ``eval/reports/prompt_comparison.{md,json}`` — a single table
across versions plus per-transition commentary explaining *why* each step should
improve, annotated with the measured deltas. This is the artifact the brief asks
for: "keep the prompts and test results so the improvement can be demonstrated."

    python -m eval.prepare_hf_dataset                 # build the eval set first
    python -m eval.compare_prompts
    python -m eval.compare_prompts --dataset eval/datasets/medical_dialogs_notes.jsonl --versions v1 v2 v3 final

NOTE: a real LLM is required (e.g. Groq GPT-OSS); extraction runs on the
configured provider.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from medextract.config import get_settings  # noqa: E402
from eval.run_eval import DEFAULT_DATASET, REPORTS, run_version  # noqa: E402

# Why each step should improve on the previous one (from the prompt CHANGELOG).
RATIONALE: Dict[str, str] = {
    "v1": "Baseline: extract-only, evidence required, status enum, output shape.",
    "v2": "Defined each assertion status with trigger cues and a physician-facing "
          "role; tightened the verbatim-evidence and 'when in doubt, leave it out' rules.",
    "v3": "Added explicit negation/uncertainty, medication-splitting, ambiguity and "
          "consistency rule blocks, plus a one-shot worked example (incl. a negated "
          "finding and a split medication).",
    "final": "Reorganized into the nine brief-mandated elements as labelled, auditable "
             "sections; worked example ends with a populated follow_up.",
}

# Metrics surfaced in the comparison table (label -> accessor).
# extraction is None on gold-less datasets; guard every accessor.
def _f1(r: Dict) -> Optional[float]: return r["extraction"]["f1"] if r["extraction"] else None
def _prec(r: Dict) -> Optional[float]: return r["extraction"]["precision"] if r["extraction"] else None
def _rec(r: Dict) -> Optional[float]: return r["extraction"]["recall"] if r["extraction"] else None

_METRICS = [
    ("extraction F1", _f1),
    ("precision", _prec),
    ("recall", _rec),
    ("unsupported rate", lambda r: r["unsupported_extraction_rate"]),
    ("incoherent rate", lambda r: r.get("incoherent_extraction_rate")),
    ("schema 1st-pass valid", lambda r: r["schema_first_pass_validity"]),
    ("repair rate", lambda r: r["repair_rate"]),
    ("ICD-10 top-1", lambda r: r["icd10_top1_accuracy"]),
    ("urgency acc", lambda r: r["urgency_accuracy"]),
]


def _fmt(v: object) -> str:
    return "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def compare(dataset: Path, versions: List[str], limit: Optional[int]) -> Dict:
    runs_dir = REPORTS / "prompt_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    reports: Dict[str, Dict] = {}
    for v in versions:
        report, outputs = run_version(dataset, v, limit)
        reports[v] = report
        out_path = runs_dir / f"{v}.jsonl"
        out_path.write_text(
            "\n".join(json.dumps(o, ensure_ascii=False) for o in outputs) + "\n",
            encoding="utf-8",
        )
        print(f"[{v}] {report['notes']} notes -> {out_path}  (F1={_fmt(_f1(report))})")

    return reports


def write_comparison(reports: Dict[str, Dict], dataset: Path) -> Path:
    versions = list(reports)
    model = reports[versions[0]]["model"] if versions else "?"
    notes = reports[versions[0]]["notes"] if versions else 0
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    provider = get_settings().llm_provider

    md: List[str] = [
        "# Prompt iteration comparison (V1 -> V2 -> V3 -> Final)",
        "",
        f"- generated: {ts}",
        f"- dataset: `{dataset}` ({notes} notes)",
        f"- provider: `{provider}`  ·  model: `{model}`",
        f"- per-note outputs: `eval/reports/prompt_runs/<version>.jsonl`",
        "",
    ]

    # metric table: rows = metrics, columns = versions
    md.append("| metric | " + " | ".join(versions) + " |")
    md.append("|---|" + "|".join(["---"] * len(versions)) + "|")
    for label, acc in _METRICS:
        md.append(f"| {label} | " + " | ".join(_fmt(acc(reports[v])) for v in versions) + " |")
    md.append("")

    # per-transition commentary with measured F1 delta
    md.append("## What changed and why")
    md.append("")
    md.append(f"**V1 —** {RATIONALE['v1']}")
    for prev, cur in zip(versions, versions[1:]):
        d = None
        a, b = _f1(reports[prev]), _f1(reports[cur])
        if a is not None and b is not None:
            d = f" (F1 {b - a:+.3f})"
        md.append("")
        md.append(f"**{prev} → {cur}{d or ''} —** {RATIONALE.get(cur, '')}")
    md.append("")

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "prompt_comparison.json").write_text(
        json.dumps({"generated": ts, "dataset": str(dataset), "model": model,
                    "reports": reports}, indent=2),
        encoding="utf-8",
    )
    md_path = REPORTS / "prompt_comparison.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return md_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(DEFAULT_DATASET))
    ap.add_argument("--versions", nargs="+", default=["v1", "v2", "v3", "final"])
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    reports = compare(Path(args.dataset), args.versions, args.limit)
    md = write_comparison(reports, Path(args.dataset))
    print(f"\ncomparison written to {md}")


if __name__ == "__main__":
    main()
