"""Command-line extraction: clinical note -> structured JSON file.

Runs the full pipeline on a single note and writes the brief's flat JSON schema
to a file (and optionally prints it). Uses whichever LLM/ICD-10 backend the
environment configures (see .env / config.py).

    python -m medextract.cli --note "Severe chest pain. Hx hypertension." -o out.json
    python -m medextract.cli --file note.txt              # -> outputs/<name>.json
    echo "cough and fever" | python -m medextract.cli --print
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .brief import to_brief
from .orchestrator import run
from .safety import NoteValidationError
from .schemas import ExtractionFailed


def _read_note(args: argparse.Namespace) -> str:
    if args.note:
        return args.note
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("provide a note via --note, --file, or stdin")


def _default_out(args: argparse.Namespace) -> Path:
    if args.file:
        stem = Path(args.file).stem
    else:
        stem = datetime.now(timezone.utc).strftime("extract_%Y%m%dT%H%M%SZ")
    return Path("outputs") / f"{stem}.json"


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract a clinical note to JSON.")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--note", help="note text")
    src.add_argument("--file", help="path to a note text file")
    ap.add_argument("-o", "--out", help="output JSON path (default: outputs/<name>.json)")
    ap.add_argument("--no-icd10", action="store_true", help="skip ICD-10 suggestions")
    ap.add_argument("--no-summary", action="store_true", help="skip the summary")
    ap.add_argument("--print", action="store_true", dest="do_print",
                    help="also print the JSON to stdout")
    args = ap.parse_args()

    note = _read_note(args)
    try:
        resp = run(note, include_icd10=not args.no_icd10, include_summary=not args.no_summary)
    except NoteValidationError as e:
        raise SystemExit(f"invalid note: {e}")
    except ExtractionFailed as e:
        raise SystemExit(f"extraction failed after repair: {e}")

    data = to_brief(resp)
    text = json.dumps(data, indent=2, ensure_ascii=False)

    out = Path(args.out) if args.out else _default_out(args)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    if args.do_print:
        print(text)
    print(f"saved -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
