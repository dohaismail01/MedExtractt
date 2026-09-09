"""Offline ICD-10-CM lookup against a local CMS CSV.

Exercised deliberately when the NLM API is unreachable (Plan G4). The CSV is a
two-column `code,description` file placed at reference/icd10cm_codes.csv. If the
file is absent, this returns [] and the caller reports no candidates.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

_CSV = Path(__file__).resolve().parents[2] / "reference" / "icd10cm_codes.csv"


@lru_cache(maxsize=1)
def _rows() -> list[tuple[str, str]]:
    if not _CSV.exists():
        return []
    out: list[tuple[str, str]] = []
    with _CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) >= 2:
                out.append((row[0].strip(), row[1].strip()))
    return out


def cms_search(term: str, max_list: int = 10) -> list[dict]:
    """Substring match on descriptions. Returns [{code, name}, ...]."""
    if not term or not term.strip():
        return []
    t = term.lower()
    hits = [{"code": c, "name": d} for c, d in _rows() if t in d.lower()]
    return hits[:max_list]
