"""ICD-10 lookup exposed to the model as a function/tool (Call 3, bonus).

The model requests the tool call; this code intercepts it, runs the real lookup
against the NLM Clinical Table Search API (with an offline CSV fallback), and
feeds the result back. The model can only report codes that came from an actual
tool result — it cannot invent a code.
"""
from __future__ import annotations

import csv
import json
from functools import lru_cache
from typing import Optional

import httpx

from . import config, llm_client
from .schema import Extraction

_NLM_URL = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
_LOCAL_CSV = config.REFERENCE_DIR / "icd10cm_codes.csv"

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lookup_icd10",
        "description": "Look up the best-matching ICD-10-CM code for a diagnosis term.",
        "parameters": {
            "type": "object",
            "properties": {
                "term": {"type": "string", "description": "The diagnosis term to code."}
            },
            "required": ["term"],
        },
    },
}


@lru_cache(maxsize=1)
def _local_index() -> dict[str, str]:
    """Load the offline CMS CSV as {lowercased description: code}, if present."""
    index: dict[str, str] = {}
    if not _LOCAL_CSV.exists():
        return index
    with _LOCAL_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) >= 2:
                code, desc = row[0].strip(), row[1].strip()
                index[desc.lower()] = code
    return index


def lookup_icd10(term: str) -> Optional[dict]:
    """Real lookup: NLM API first, offline CSV fallback. Returns {code, description}
    or None if nothing matched."""
    if not term or not term.strip():
        return None

    # 1. NLM Clinical Table Search API.
    try:
        resp = httpx.get(
            _NLM_URL,
            params={"sf": "code,name", "terms": term, "maxList": 1},
            timeout=8.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # Response shape: [total, [codes], null, [[code, name], ...]]
        rows = data[3] if len(data) > 3 else []
        if rows:
            return {"code": rows[0][0], "description": rows[0][1]}
    except (httpx.HTTPError, ValueError, IndexError, KeyError):
        pass  # fall through to offline

    # 2. Offline CSV fallback (substring match on descriptions).
    for desc, code in _local_index().items():
        if term.lower() in desc:
            return {"code": code, "description": desc}
    return None


def code_diagnoses(extraction: Extraction) -> dict[str, Optional[dict]]:
    """Model-invoked coding of the diagnosis list.

    Presents the diagnoses and the lookup_icd10 tool to the model, executes each
    requested tool call for real, and returns {diagnosis: {code, description}|None}.
    Falls back to direct lookups if the model emits no tool calls.
    """
    diagnoses = extraction.diagnosis
    if not diagnoses:
        return {}

    system = (
        "You map diagnosis terms to ICD-10-CM codes. For EACH diagnosis provided, "
        "call lookup_icd10 with that term. Only report codes returned by the tool; "
        "never invent a code."
    )
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Diagnoses: " + json.dumps(diagnoses)},
    ]

    results: dict[str, Optional[dict]] = {d: None for d in diagnoses}

    try:
        msg = llm_client.chat_with_tools(messages, tools=[TOOL_SCHEMA])
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for call in tool_calls:
                args = json.loads(call.function.arguments or "{}")
                term = args.get("term", "")
                match = lookup_icd10(term)
                # Attribute the result back to the closest requested diagnosis.
                key = _closest_key(term, results)
                if key is not None:
                    results[key] = match
            return results
    except Exception:  # noqa: BLE001 - bonus feature degrades gracefully
        pass

    # Fallback: code each diagnosis directly in code.
    for d in diagnoses:
        results[d] = lookup_icd10(d)
    return results


def _closest_key(term: str, results: dict) -> Optional[str]:
    term_l = term.lower()
    for key in results:
        if key.lower() == term_l or term_l in key.lower() or key.lower() in term_l:
            return key
    # default to the first still-unfilled key
    for key, val in results.items():
        if val is None:
            return key
    return None
