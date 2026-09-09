"""Download the Kaggle clinical-notes dataset into ./data/ (gitignored).

Dataset: Patient Diaries and Clinical Notes Dataset
https://www.kaggle.com/datasets/jennifercynthia66/patient-diaries-and-clinical-notes-dataset

Requires Kaggle credentials, one of:
  - ~/.kaggle/kaggle.json   (download from your Kaggle account -> Settings -> API)
  - env vars KAGGLE_USERNAME and KAGGLE_KEY

Run from the project root:  python -m scripts.download_data
The dataset is copied into ./data/ so the rest of the pipeline reads from a
stable local path rather than kagglehub's cache.
"""
from __future__ import annotations

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SLUG = "jennifercynthia66/patient-diaries-and-clinical-notes-dataset"


def main() -> None:
    import kagglehub  # imported here so the module loads without the dep present

    print(f"Downloading {SLUG} ...")
    cache_path = Path(kagglehub.dataset_download(SLUG))
    print("Downloaded to cache:", cache_path)

    DATA_DIR.mkdir(exist_ok=True)
    copied = 0
    for src in cache_path.rglob("*"):
        if src.is_file():
            dest = DATA_DIR / src.name
            shutil.copy2(src, dest)
            copied += 1
            print("  ->", dest.relative_to(PROJECT_ROOT))
    print(f"Copied {copied} file(s) into {DATA_DIR.relative_to(PROJECT_ROOT)}/")


if __name__ == "__main__":
    main()
