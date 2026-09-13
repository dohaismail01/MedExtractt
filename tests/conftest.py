"""Test isolation.

The suite must be hermetic (SPEC.md §8: the offline ``stub`` provider keeps
tests and a zero-config run working with no API key). A developer's local .env
may point the pipeline at a real LLM (e.g. Groq); force the stub here BEFORE
``medextract.config`` is imported so environment variables win over .env and no
test ever makes a network call.
"""

import os

os.environ["MEDEXTRACT_LLM_PROVIDER"] = "stub"
os.environ["MEDEXTRACT_MODEL"] = "stub-heuristic"
os.environ["MEDEXTRACT_LLM_BASE_URL"] = ""
# The default ICD-10 backend is the live NLM online lookup; force the offline
# local source in tests so no test makes a network call.
os.environ["ICD10_BACKEND"] = "local_sqlite"
