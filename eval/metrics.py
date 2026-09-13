"""Evaluation metrics (CLAUDE.md §6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


def prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3)}


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((pct / 100.0) * (len(s) - 1)))
    return s[k]


@dataclass
class Accumulator:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    icd_tp: int = 0
    icd_total: int = 0
    icd_abstain: int = 0
    icd_invalid: int = 0
    urg_correct: int = 0
    urg_total: int = 0
    unsupported: int = 0
    first_pass_valid: int = 0
    repaired: int = 0
    notes: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    tool_calls: List[int] = field(default_factory=list)

    def report(self, prompt_version: str, model: str) -> Dict:
        return {
            "notes": self.notes,
            "prompt_version": prompt_version,
            "model": model,
            "extraction": prf(self.tp, self.fp, self.fn),
            "unsupported_extraction_rate": round(self.unsupported / max(1, self.tp + self.fp), 3),
            "schema_first_pass_validity": round(self.first_pass_valid / max(1, self.notes), 3),
            "repair_rate": round(self.repaired / max(1, self.notes), 3),
            "icd10_top1_accuracy": round(self.icd_tp / self.icd_total, 3) if self.icd_total else None,
            "icd10_abstention_rate": round(self.icd_abstain / self.icd_total, 3) if self.icd_total else None,
            "icd10_invalid_code_rate": round(self.icd_invalid / max(1, self.icd_total), 3),
            "urgency_accuracy": round(self.urg_correct / self.urg_total, 3) if self.urg_total else None,
            "latency_ms_p50": round(percentile(self.latencies_ms, 50), 1),
            "latency_ms_p95": round(percentile(self.latencies_ms, 95), 1),
            "mean_icd10_tool_calls": round(sum(self.tool_calls) / len(self.tool_calls), 2) if self.tool_calls else 0,
        }
