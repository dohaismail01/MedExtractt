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
# The default ICD-10 backend is the live NLM online lookup; force the offline
# local source in tests so no test makes a network call.
os.environ["ICD10_BACKEND"] = "local_sqlite"

import pytest


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
