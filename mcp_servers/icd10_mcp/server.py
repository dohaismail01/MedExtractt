"""icd10_mcp — a standalone MCP server for ICD-10-CM lookup (Plan §9).

Two read-only tools:
  icd10_lookup_code       applies the accept rule, returns one code or null
  icd10_search_candidates returns the ranked candidate list, no accept rule

Runs over stdio alongside FastAPI, and standalone under MCP Inspector:
    python -m mcp_servers.icd10_mcp.server

A null `code` is a correct answer. Every lookup logs the argument, the full
candidate list, the score, and the reason — a null with no logged reason is a bug.
"""
from __future__ import annotations

import re
import sys

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field
from rapidfuzz import fuzz

from .cms_fallback import cms_search
from .nlm import nlm_search

# Accept thresholds (mirror app.config §2; kept local so the server stands alone).
ICD_ACCEPT = 90
ICD_ACCEPT_SINGLE = 80

mcp = FastMCP("icd10_mcp")


def _normalise(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower().strip())
    return " ".join(s.split())


def _log(msg: str) -> None:
    # stderr, so it never corrupts the stdio JSON-RPC channel.
    print(f"[icd10_mcp] {msg}", file=sys.stderr, flush=True)


class LookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    diagnosis: str = Field(..., min_length=1, max_length=200,
                           description="Exact diagnosis string as extracted from the note.")


def _candidates(diagnosis: str) -> tuple[list[dict], str]:
    """NLM first, CMS CSV fallback. Returns (candidates, source)."""
    hits = nlm_search(diagnosis)
    if hits:
        return hits, "nlm"
    return cms_search(diagnosis), "cms_csv"


# NOTE: tool annotations (readOnlyHint/destructiveHint/idempotentHint/openWorldHint,
# Plan §9.3) require a newer mcp SDK than the pinned 1.2.0, which rejects the
# `annotations=` kwarg. Both tools are read-only and idempotent; re-add the hints
# once the SDK is bumped.
@mcp.tool()
def icd10_lookup_code(diagnosis: str) -> dict:
    """Look up the ICD-10-CM code for one diagnosis string.

    Returns null for `code` when no confident match exists. A null result is a
    correct answer — do not substitute a code from your own knowledge.
    """
    params = LookupInput(diagnosis=diagnosis)
    cands, source = _candidates(params.diagnosis)
    if not cands:
        _log(f"lookup '{diagnosis}' -> null (no_candidates)")
        return {"code": None, "name": None, "score": 0, "reason": "no_candidates",
                "source": source, "candidates": []}

    score = int(fuzz.token_set_ratio(_normalise(params.diagnosis), _normalise(cands[0]["name"])))
    if score >= ICD_ACCEPT:
        _log(f"lookup '{diagnosis}' -> {cands[0]['code']} (high_score={score})")
        return {**cands[0], "score": score, "reason": "high_score",
                "source": source, "candidates": cands}
    if len(cands) == 1 and score >= ICD_ACCEPT_SINGLE:
        _log(f"lookup '{diagnosis}' -> {cands[0]['code']} (sole_candidate={score})")
        return {**cands[0], "score": score, "reason": "sole_candidate",
                "source": source, "candidates": cands}

    _log(f"lookup '{diagnosis}' -> null (ambiguous score={score})")
    return {"code": None, "name": None, "score": score,
            "reason": f"ambiguous score={score}", "source": source, "candidates": cands}


@mcp.tool()
def icd10_search_candidates(diagnosis: str) -> dict:
    """Return the ranked ICD-10-CM candidate list for a diagnosis, no accept rule.
    For transparency and debugging — lets a caller see near-misses."""
    params = LookupInput(diagnosis=diagnosis)
    cands, source = _candidates(params.diagnosis)
    return {"diagnosis": params.diagnosis, "source": source, "candidates": cands}


if __name__ == "__main__":
    mcp.run()
