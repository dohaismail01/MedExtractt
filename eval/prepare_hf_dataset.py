"""Convert a HuggingFace clinical-notes dataset into the eval JSONL format.

Default source: ``chenhaodev/medical-dialogs-notes`` (225 rows; columns
``id``, ``dataset_source``, ``dialogue``, ``clinical_note``). We extract the
``clinical_note`` field as the note to run the pipeline on. The dataset has no
gold annotations for our fields, so rows are written WITHOUT a ``gold`` key —
the harness then reports only the label-free metrics (schema validity,
unsupported-extraction rate, repair rate, ICD-10 abstention, latency), not P/R/F1.

Writes ``eval/datasets/<name>.jsonl`` as ``{"id": ..., "note": ...}`` per line.

    python -m eval.prepare_hf_dataset                       # full set
    python -m eval.prepare_hf_dataset --limit 50            # first 50 notes
    python -m eval.prepare_hf_dataset --field dialogue      # use the dialogue instead

No heavy dependency is required: the HF datasets-server API is used over httpx.
If the ``datasets`` library is installed it is used instead (offline-friendly).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import httpx

ROOT = Path(__file__).resolve().parent
DATASETS = ROOT / "datasets"
_API = "https://datasets-server.huggingface.co/rows"


def _via_datasets_lib(dataset: str, split: str) -> Optional[List[Dict]]:
    """Use the `datasets` library if available; else None."""
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError:
        return None
    ds = load_dataset(dataset, split=split)
    return [dict(r) for r in ds]


def _via_api(dataset: str, config: str, split: str) -> Iterator[Dict]:
    """Page through the public HF datasets-server API (no local library)."""
    offset, page = 0, 100
    while True:
        r = httpx.get(_API, params={"dataset": dataset, "config": config,
                                    "split": split, "offset": offset, "length": page},
                      timeout=60)
        r.raise_for_status()
        rows = r.json().get("rows", [])
        if not rows:
            return
        for item in rows:
            yield item["row"]
        offset += len(rows)


def convert(dataset: str, field: str, out: Path, limit: Optional[int],
            config: str = "default", split: str = "train") -> int:
    records = _via_datasets_lib(dataset, split)
    source = records if records is not None else _via_api(dataset, config, split)

    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for row in source:
            note = (row.get(field) or "").strip()
            if not note:
                continue
            rec = {"id": row.get("id"), "note": note}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            if limit and n >= limit:
                break
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="chenhaodev/medical-dialogs-notes")
    ap.add_argument("--field", default="clinical_note",
                    help="row column to use as the note (e.g. clinical_note | dialogue)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None, help="output JSONL path")
    args = ap.parse_args()

    name = args.dataset.split("/")[-1].replace("-", "_")
    out = Path(args.out) if args.out else DATASETS / f"{name}.jsonl"
    count = convert(args.dataset, args.field, out, args.limit)
    print(f"wrote {count} notes -> {out}")
    print(f"run:  python -m eval.run_eval --dataset {out}")


if __name__ == "__main__":
    main()
