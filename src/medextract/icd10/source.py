"""ICD-10 data backend adapter (SPEC.md §4).

One interface, swappable implementation. ``LocalSqliteSource`` loads the bundled
ICD-10-CM tabular file into an in-memory SQLite FTS5 table for retrieval and
scores candidates with rapidfuzz. The agent must not know which is in use.

Only ICD-10-CM (diagnosis) is provided here; ``supports_pcs`` is False, so the
agent leaves procedures uncoded (approach.md §5 / SPEC.md §4).
"""

from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol

import httpx
from rapidfuzz import fuzz

REFERENCE = Path(__file__).resolve().parent.parent.parent.parent / "reference" / "icd10_common.csv"

_STOP = {"unspecified", "of", "the", "with", "without", "and", "disorder",
         "disease", "syndrome", "nos"}


@dataclass
class Candidate:
    code: str
    description: str
    score: float  # 0..1


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in _STOP]


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


class LocalSqliteSource:
    supports_pcs = False

    def __init__(self, path: Path = REFERENCE) -> None:
        self.rows = []
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                r["keywords"] = r.get("keywords", "")
                self.rows.append(r)
        self._codes = {r["code"].upper(): r for r in self.rows}
        self._db = sqlite3.connect(":memory:")
        self._fts = True
        try:
            self._db.execute("CREATE VIRTUAL TABLE codes USING fts5(code, description, keywords)")
        except sqlite3.OperationalError:  # pragma: no cover - fts5 unavailable
            self._fts = False
            self._db.execute("CREATE TABLE codes (code, description, keywords)")
        self._db.executemany(
            "INSERT INTO codes (code, description, keywords) VALUES (?, ?, ?)",
            [(r["code"], r["description"], r["keywords"].replace("|", " ")) for r in self.rows],
        )
        self._db.commit()

    def _retrieve(self, query: str) -> List[dict]:
        tokens = _tokens(query)
        if self._fts and tokens:
            fts_q = " OR ".join(tokens)
            try:
                cur = self._db.execute(
                    "SELECT code, description, keywords FROM codes WHERE codes MATCH ?",
                    (fts_q,),
                )
                hits = [dict(zip(("code", "description", "keywords"), row)) for row in cur.fetchall()]
                if hits:
                    return hits
            except sqlite3.OperationalError:
                pass
        return [{"code": r["code"], "description": r["description"],
                 "keywords": r["keywords"].replace("|", " ")} for r in self.rows]

    def _score(self, query: str, row: dict) -> float:
        q = query.lower().strip()
        # exact alias phrase match on the original pipe-separated keywords
        raw_aliases = [a.strip().lower() for a in self._codes[row["code"].upper()]["keywords"].split("|")]
        if q in raw_aliases:
            return 1.0
        best = 0.0
        for target in raw_aliases + [row["description"].lower()]:
            best = max(best, fuzz.token_set_ratio(q, target) / 100.0)
        return round(best, 3)

    def search(self, query: str, code_type: str = "CM", limit: int = 5) -> List[Candidate]:
        if code_type != "CM":
            return []
        cands = [Candidate(r["code"], r["description"], self._score(query, r))
                 for r in self._retrieve(query)]
        cands = [c for c in cands if c.score > 0]
        cands.sort(key=lambda c: c.score, reverse=True)
        return cands[:limit]

    def lookup(self, code: str) -> Optional[Candidate]:
        r = self._codes.get(code.upper())
        return Candidate(r["code"], r["description"], 1.0) if r else None

    def validate(self, code: str) -> bool:
        return bool(code) and code.upper() in self._codes

    def get_category(self, code: str) -> List[Candidate]:
        prefix = code.split(".")[0].upper()
        return [Candidate(r["code"], r["description"], 0.5)
                for r in self.rows if r["code"].upper().split(".")[0] == prefix]


class NlmOnlineSource:
    """Online ICD-10-CM lookup via the NLM Clinical Table Search Service.

    Public US National Library of Medicine API (no key, no auth):
    https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search

    Only the extracted clinical *term* (e.g. "hypertension") is sent — never the
    note or any PHI. On any network error it transparently falls back to the
    bundled local source so the agent keeps working offline.
    """

    supports_pcs = False  # NLM endpoint is ICD-10-CM only
    _URL = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"

    def __init__(self, timeout: float = 8.0, fallback: Optional[Icd10Source] = None) -> None:
        self.timeout = timeout
        self._fallback = fallback if fallback is not None else LocalSqliteSource()

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
            return []
        data = self._get({"terms": query, "sf": "code,name", "df": "code,name",
                          "maxList": max(limit, 7)})
        if data is None:
            return self._fallback.search(query, code_type, limit)
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
            return self._fallback.lookup(code)
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
            return self._fallback.get_category(code)
        pairs = data[3] if len(data) > 3 and isinstance(data[3], list) else []
        return [Candidate(code=r[0], description=r[1] if len(r) > 1 else "", score=0.5)
                for r in pairs if r and r[0].upper().split(".")[0] == prefix]


def get_source(name: str) -> Icd10Source:
    """Select the ICD-10 backend by name (SPEC.md §4).

    - "nlm" / "online" -> live NLM Clinical Table Search Service (+ local fallback)
    - "local_sqlite" (default) -> bundled ICD-10-CM CSV in in-memory SQLite FTS
    """
    if name in ("nlm", "online"):
        return NlmOnlineSource()
    return LocalSqliteSource()
