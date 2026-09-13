"""Test isolation.

The suite must be hermetic (CLAUDE.md §8: the offline ``stub`` provider keeps
tests and a zero-config run working with no API key). A developer's local .env
may point the pipeline at a real LLM (e.g. Groq); force the stub here BEFORE
``medextract.config`` is imported so environment variables win over .env and no
test ever makes a network call.
"""

import os

os.environ["MEDEXTRACT_LLM_PROVIDER"] = "stub"
os.environ["MEDEXTRACT_MODEL"] = "stub-heuristic"
os.environ["MEDEXTRACT_LLM_BASE_URL"] = ""
