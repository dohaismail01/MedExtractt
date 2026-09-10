"""Kaggle dataset label lookup.

The Kaggle `label` (depression / no depression) is a CLASSIFICATION target, NOT
one of the 10 extraction fields. It is served from its own endpoint and shown
separately in the UI, so it never contaminates the extraction contract.

Looks a note's exact text up against the dataset CSVs (in ./data, gitignored).
Returns None when the note isn't a dataset row (e.g. a pasted custom note) or
when the data files aren't present.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from typing import Optional

from . import config

_CSVS = ("clinical_notes.csv", "patient_diaries.csv")
_DATA_DIR = config.PROJECT_ROOT / "data"


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


@lru_cache(maxsize=1)
def _index() -> dict[str, str]:
    """{normalised note text: label} built once from the dataset CSVs."""
    index: dict[str, str] = {}
    for name in _CSVS:
        path = _DATA_DIR / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                text, label = row.get("text"), row.get("label")
                if text and label:
                    index[_norm(text)] = label.strip()
    return index


def available() -> bool:
    return bool(_index())


def lookup(note: str) -> Optional[str]:
    """The dataset label for an exact note match, else None."""
    if not note or not note.strip():
        return None
    return _index().get(_norm(note))
