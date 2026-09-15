"""ICD-10 data backend adapter (SPEC.md §4).

The ICD-10 coding agent's mission is to **search online** for a code — there is
no local code database and no local fallback. ``NlmOnlineSource`` queries the
public US National Library of Medicine Clinical Table Search Service for
ICD-10-CM (diagnosis) codes. If the service cannot be reached, the source
returns nothing and the agent abstains (``code: null``, ``needs_review: true``)
rather than serving canned data.

ICD-10-PCS (procedures) has no free online search service, so ``supports_pcs``
is False and the agent leaves procedures uncoded (``resolution_path`` entry
``"pcs_unsupported"``). Only the extracted clinical *term* (e.g. "hypertension")
is ever sent to the service — never the note or any PHI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Protocol

import httpx
from rapidfuzz import fuzz


@dataclass
class Candidate:
    code: str
    description: str
    score: float  # 0..1


def _nlm_score(query: str, name: str) -> float:
    """Confidence for an NLM candidate. Parentheticals (e.g. "(primary)") are
    stripped so they don't distort the match; exact name match -> 1.0."""
    n = re.sub(r"\(.*?\)", "", name).lower().strip()
    n = re.sub(r"\s+", " ", n)
    if query == n:
        return 1.0
    return round(fuzz.token_sort_ratio(query, n) / 100.0, 3)


class Icd10Source(Protocol):
    supports_pcs: bool

    def search(self, query: str, code_type: str = "CM", limit: int = 5) -> List[Candidate]: ...
    def lookup(self, code: str) -> Optional[Candidate]: ...
    def validate(self, code: str) -> bool: ...
    def get_category(self, code: str) -> List[Candidate]: ...


class NlmOnlineSource:
    """Online ICD-10-CM lookup via the NLM Clinical Table Search Service.

    Public US National Library of Medicine API (no key, no auth):
    https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search

    Online-only: on any network/HTTP error the call returns nothing (search ->
    [], lookup -> None, validate -> False), so the agent abstains rather than
    inventing or serving local data. ICD-10-CM (diagnosis) only; ``supports_pcs``
    is False because there is no comparable free online ICD-10-PCS service.
    """

    supports_pcs = False
    _URL = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout

    def _get(self, params: dict) -> Optional[list]:
        """Return the NLM response array, or None on any failure."""
        try:
            resp = httpx.get(self._URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError):
            return None

    def search(self, query: str, code_type: str = "CM", limit: int = 5) -> List[Candidate]:
        if code_type != "CM":
            return []  # no online ICD-10-PCS service; agent abstains on procedures
        data = self._get({"terms": query, "sf": "code,name", "df": "code,name",
                          "maxList": max(limit, 7)})
        if data is None:
            return []  # service unreachable -> no candidates -> agent abstains
        # shape: [total, [codes], null|hash, [[code, name], ...]]
        pairs = data[3] if len(data) > 3 and isinstance(data[3], list) else []
        q = query.lower().strip()
        cands: List[Candidate] = []
        for row in pairs:
            if not row:
                continue
            code, name = row[0], (row[1] if len(row) > 1 else "")
            cands.append(Candidate(code=code, description=name, score=_nlm_score(q, name)))
        # token_sort_ratio differentiates candidates (unlike token_set_ratio, which
        # returns 1.0 for any subset match); a generic single-word term stays below
        # the accept threshold so the agent flags it needs_review rather than
        # over-committing to one of many plausible codes.
        cands.sort(key=lambda c: c.score, reverse=True)
        return cands[:limit]

    def lookup(self, code: str) -> Optional[Candidate]:
        data = self._get({"terms": code, "sf": "code", "df": "code,name", "maxList": 7})
        if data is None:
            return None
        pairs = data[3] if len(data) > 3 and isinstance(data[3], list) else []
        target = code.upper().strip()
        for row in pairs:
            if row and row[0].upper() == target:
                return Candidate(code=row[0], description=row[1] if len(row) > 1 else "", score=1.0)
        return None

    def validate(self, code: str) -> bool:
        return self.lookup(code) is not None

    def get_category(self, code: str) -> List[Candidate]:
        prefix = code.split(".")[0].upper()
        data = self._get({"terms": prefix, "sf": "code", "df": "code,name", "maxList": 20})
        if data is None:
            return []
        pairs = data[3] if len(data) > 3 and isinstance(data[3], list) else []
        return [Candidate(code=r[0], description=r[1] if len(r) > 1 else "", score=0.5)
                for r in pairs if r and r[0].upper().split(".")[0] == prefix]


def get_source(name: str = "nlm") -> Icd10Source:
    """The ICD-10 backend. Online-only: always the live NLM Clinical Table Search
    Service. There is no local backend or fallback by design (the agent's mission
    is to search online); tests inject a fake source instead of hitting the network."""
    return NlmOnlineSource()
