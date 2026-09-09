"""NLM Clinical Table Search API client for ICD-10-CM.

    GET https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search
        ?sf=code,name&terms=<diagnosis>&maxList=10
    -> [total, [codes...], null, [[code, name], ...]]
"""
from __future__ import annotations

import httpx

_URL = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"


def nlm_search(term: str, max_list: int = 10, timeout: float = 8.0) -> list[dict]:
    """Return a ranked candidate list [{code, name}, ...]; [] on any failure."""
    if not term or not term.strip():
        return []
    try:
        resp = httpx.get(
            _URL,
            params={"sf": "code,name", "terms": term, "maxList": max_list},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data[3] if len(data) > 3 else []
        return [{"code": r[0], "name": r[1]} for r in rows if len(r) >= 2]
    except (httpx.HTTPError, ValueError, IndexError, KeyError):
        return []
