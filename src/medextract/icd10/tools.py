"""Tool definitions exposed to the ICD-10 agent loop (SPEC.md §4).

Thin wrappers over the source adapter. Each call is counted by the agent so the
per-term and per-note bounds are enforced. No LLM calls happen here.
"""

from __future__ import annotations

from typing import List, Optional

from .source import Candidate, Icd10Source


class Icd10Tools:
    def __init__(self, source: Icd10Source) -> None:
        self.source = source
        self.calls = 0

    @property
    def supports_pcs(self) -> bool:
        return self.source.supports_pcs

    def search_codes(self, query: str, code_type: str = "CM", search_by: str = "description") -> List[Candidate]:
        self.calls += 1
        return self.source.search(query, code_type=code_type)

    def lookup_code(self, code: str) -> Optional[Candidate]:
        self.calls += 1
        return self.source.lookup(code)

    def validate_code(self, code: str) -> bool:
        self.calls += 1
        return self.source.validate(code)

    def get_category(self, code: str) -> List[Candidate]:
        self.calls += 1
        return self.source.get_category(code)
