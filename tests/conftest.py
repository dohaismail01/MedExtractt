"""Test isolation.

The suite must be hermetic (SPEC.md §8: the offline ``stub`` provider keeps
tests and a zero-config run working with no API key). A developer's local .env
may point the pipeline at a real LLM (e.g. Groq); force the stub here BEFORE
``medextract.config`` is imported so environment variables win over .env and no
test ever makes a network call.
"""

import json
import os

os.environ["MEDEXTRACT_LLM_PROVIDER"] = "stub"
os.environ["MEDEXTRACT_MODEL"] = "stub-heuristic"
os.environ["MEDEXTRACT_LLM_BASE_URL"] = ""

import pytest

from medextract.icd10.source import Candidate


# The ICD-10 agent is online-only (NLM) in production; there is no local backend.
# For hermetic tests we inject this deterministic fake source instead of hitting
# the network — it maps a handful of clinical terms to their real CM codes.
_FAKE_CM = {
    "hypertension": ("I10", "Essential (primary) hypertension"),
    "htn": ("I10", "Essential (primary) hypertension"),
    "myocardial infarction": ("I21.9", "Acute myocardial infarction, unspecified"),
    "acute myocardial infarction": ("I21.9", "Acute myocardial infarction, unspecified"),
    "atrial fibrillation": ("I48.91", "Unspecified atrial fibrillation"),
    "afib": ("I48.91", "Unspecified atrial fibrillation"),
    "pneumonia": ("J18.9", "Pneumonia, unspecified organism"),
    "asthma": ("J45.909", "Unspecified asthma, uncomplicated"),
    "type 2 diabetes": ("E11.9", "Type 2 diabetes mellitus without complications"),
    "diabetes": ("E11.9", "Type 2 diabetes mellitus without complications"),
    "copd": ("J44.9", "Chronic obstructive pulmonary disease, unspecified"),
    "sepsis": ("A41.9", "Sepsis, unspecified organism"),
    "stroke": ("I63.9", "Cerebral infarction, unspecified"),
}


class FakeIcd10Source:
    """Deterministic, offline stand-in for NlmOnlineSource. CM only (no PCS),
    matching production: procedures abstain because there is no online PCS source."""

    supports_pcs = False

    def __init__(self, table=None):
        self.table = table if table is not None else _FAKE_CM
        self._codes = {c.upper(): (c, d) for c, d in self.table.values()}

    def search(self, query, code_type="CM", limit=5):
        if code_type != "CM":
            return []  # no online PCS -> abstain
        q = " ".join(query.lower().split())
        if q in self.table:
            code, desc = self.table[q]
            return [Candidate(code, desc, 1.0)]
        # loose containment match (lower score) so unknown terms return nothing
        for alias, (code, desc) in self.table.items():
            if alias in q or q in alias:
                return [Candidate(code, desc, 0.85)]
        return []

    def lookup(self, code):
        r = self._codes.get(code.upper())
        return Candidate(r[0], r[1], 1.0) if r else None

    def validate(self, code):
        return bool(code) and code.upper() in self._codes

    def get_category(self, code):
        return []


@pytest.fixture(autouse=True)
def _offline_icd10(monkeypatch):
    """No test may hit the network for ICD-10. Any agent built via get_source()
    (e.g. inside orchestrator.run) gets the deterministic FakeIcd10Source."""
    from medextract.icd10 import agent as agent_mod
    monkeypatch.setattr(agent_mod, "get_source", lambda name="nlm": FakeIcd10Source())


class ScriptedClient:
    """Deterministic LLM double that returns a fixed sequence of raw responses.

    Lets a test inject exact (including hallucinated / malformed) model output so
    the pipeline's validation, grounding, and repair behavior can be asserted
    without a real model. The last response repeats if the loop asks for more.
    """

    name = "scripted"

    def __init__(self, outputs):
        self.outputs = [o if isinstance(o, str) else json.dumps(o) for o in outputs]
        self.calls = 0

    def complete(self, system, user):
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return out


@pytest.fixture
def scripted_run(monkeypatch):
    """Return ``run_with(note, outputs, **kwargs)`` that runs the real
    orchestrator pipeline but with a ScriptedClient standing in for the LLM."""
    from medextract import orchestrator

    def run_with(note, outputs, **kwargs):
        client = ScriptedClient(outputs)
        monkeypatch.setattr(orchestrator, "get_client", lambda cfg: client)
        resp = orchestrator.run(note, **kwargs)
        return resp, client

    return run_with
