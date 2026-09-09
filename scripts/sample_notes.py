"""Print a few notes from the Kaggle dataset for quick manual testing.

Usage:  python -m scripts.sample_notes [n]

Reads the `text` column of data/clinical_notes.csv. These are short
depression-screening texts, not full clinical notes, so most extraction fields
will correctly be empty — useful for exercising the guardrails.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

CSV = Path(__file__).resolve().parent.parent / "data" / "clinical_notes.csv"


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    df = pd.read_csv(CSV)
    for i, row in df.sample(min(n, len(df)), random_state=0).iterrows():
        print(f"[{row.get('label', '?')}] {row['text']}")


if __name__ == "__main__":
    main()
