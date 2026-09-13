"""Prompt loader. Prompts live in .md files, versioned by filename."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@lru_cache
def get_prompt(name: str, version: str | None = None) -> str:
    """Load a prompt. ``get_prompt('extraction', 'v1')`` -> extraction_v1.md;
    ``get_prompt('repair')`` -> repair.md."""
    fname = f"{name}_{version}.md" if version else f"{name}.md"
    path = _DIR / fname
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {fname}")
    return path.read_text(encoding="utf-8")
