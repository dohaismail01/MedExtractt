"""Bounded ICD-10 coding agent (SPEC.md §4).

Agentic in a narrow, defensible sense: it makes bounded search decisions to
resolve an already-validated term. It cannot create clinical facts. Every step
is recorded in ``resolution_path``; tool calls are capped per-term and per-note.
Abstention (code=null, needs_review=true) is a success mode, not a failure.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..config import Settings
from ..schemas import ClinicalFact, ExtractionResult, ICD10Suggestion, Status
from .source import Candidate, Icd10Source, get_source
from .tools import Icd10Tools

# Statuses worth coding. Negated / family_history are excluded: coding a denied
# condition or a relative's condition would misrepresent the patient's record.
_CODEABLE = {Status.PRESENT, Status.HISTORICAL, Status.UNCERTAIN}

_QUALIFIERS = re.compile(
    r"\b(acute|chronic|severe|mild|moderate|possible|likely|suspected|bilateral|"
    r"left|right|upper|lower|unspecified)\b",
    re.I,
)


class Icd10Agent:
    def __init__(self, source: Optional[Icd10Source] = None, cfg: Optional[Settings] = None):
        from ..config import settings as default
        self.cfg = cfg or default
        self.source = source or get_source(self.cfg.icd10_backend)

    def _abstain(self, term: str, path: List[str], conf: float = 0.0,
                 code_system: Optional[str] = None) -> ICD10Suggestion:
        path.append("abstain")
        return ICD10Suggestion(source_term=term, code=None, confidence=conf,
                               needs_review=True, code_system=code_system,
                               resolution_path=path)

    def resolve(self, term: str, tools: Icd10Tools, code_type: str = "CM") -> ICD10Suggestion:
        cfg = self.cfg
        path: List[str] = []
        code_system = "ICD-10-CM" if code_type == "CM" else "ICD-10-PCS"

        if code_type == "PCS" and not tools.supports_pcs:
            path.append("pcs_unsupported")
            return self._abstain(term, path, code_system=None)

        term_calls = 0

        def can_call() -> bool:
            return (term_calls < cfg.max_icd10_tool_calls_per_term
                    and tools.calls < cfg.max_icd10_tool_calls_per_note)

        def search(q: str) -> Optional[Candidate]:
            nonlocal term_calls
            if not can_call():
                path.append("budget_exhausted")
                return None
            term_calls += 1
            res = tools.search_codes(q, code_type=code_type)
            path.append(f"search:{q}")
            return res[0] if res else None

        # 1) direct search
        best = search(term)

        # 2) broaden: drop modifiers
        if (best is None or best.score < cfg.icd10_accept_threshold):
            broadened = re.sub(r"\s+", " ", _QUALIFIERS.sub("", term)).strip()
            if broadened and broadened.lower() != term.lower() and can_call():
                path.append("broaden:drop_modifier")
                cand = search(broadened)
                if cand and (best is None or cand.score > best.score):
                    best = cand

        # 3) broaden: head noun
        if (best is None or best.score < cfg.icd10_accept_threshold):
            head = term.split()[-1] if term.split() else term
            if head.lower() != term.lower() and can_call():
                path.append("broaden:head_noun")
                cand = search(head)
                if cand and (best is None or cand.score > best.score):
                    best = cand

        # abstain on weak / no candidate
        if best is None or best.score < cfg.icd10_confidence_threshold:
            return self._abstain(term, path, conf=(best.score if best else 0.0),
                                 code_system=code_system)

        # validate before returning (validated codes only)
        if not can_call():
            path.append("budget_exhausted")
            return self._abstain(term, path, conf=best.score, code_system=code_system)
        term_calls += 1
        valid = tools.validate_code(best.code)
        path.append(f"validate:{best.code}:{'ok' if valid else 'invalid'}")
        if not valid:
            return self._abstain(term, path, conf=best.score, code_system=code_system)

        needs_review = best.score < cfg.icd10_accept_threshold
        path.append("accept:needs_review" if needs_review else "accept")
        return ICD10Suggestion(
            source_term=term, code=best.code, description=best.description,
            code_system=code_system, confidence=best.score, needs_review=needs_review,
            resolution_path=path,
        )

    def code_result(self, result: ExtractionResult) -> Tuple[List[ICD10Suggestion], int]:
        tools = Icd10Tools(self.source)
        out: List[ICD10Suggestion] = []
        seen = set()

        def handle(facts: List[ClinicalFact], code_type: str) -> None:
            for f in facts:
                # Never code negated / family-history facts, regardless of type:
                # doing so would misrepresent the patient's record.
                if f.status not in _CODEABLE:
                    continue
                key = (f.text.lower(), code_type)
                if key in seen:
                    continue
                seen.add(key)
                out.append(self.resolve(f.text, tools, code_type=code_type))

        handle(list(result.diagnosis) + list(result.medical_history), "CM")
        handle(list(result.procedures), "PCS")
        return out, tools.calls
