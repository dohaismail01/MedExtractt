"""Central configuration: models, thresholds, and all constants (Plan §2).

Nothing tunable is written inline elsewhere, so a model swap or threshold
change is a one-line edit here. Decoding params are pinned identically across
all four prompt versions — if temperature or model varied between V1 and Final,
the comparison would measure two things at once and prove neither.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root regardless of where uvicorn is launched.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# --- Paths ---
PROMPTS_DIR = PROJECT_ROOT / "prompts"
EVAL_DIR = PROJECT_ROOT / "eval"
EVAL_RESULTS_DIR = EVAL_DIR / "results"
EVAL_CACHE_DIR = EVAL_DIR / "cache"
REFERENCE_DIR = PROJECT_ROOT / "reference"

# --- Provider selection ---
PROVIDER = os.getenv("PROVIDER", "groq").lower()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

# Models (Plan §2). Primary for the final pipeline; iteration model for sweeps.
MODEL_PRIMARY = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
MODEL_ITER = os.getenv("GROQ_MODEL_FAST", "openai/gpt-oss-20b")
MODEL_LOCAL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

# --- Decoding params, pinned across all versions ---
TEMPERATURE = 0.0
TOP_P = 1.0
SEED = 42  # where the provider accepts it
MAX_TOKENS_CALL1 = 1024
MAX_TOKENS_CALL2 = 512
MAX_TOKENS_CALL3 = 512

# --- Repair / HTTP resilience ---
REPAIR_MAX_ATTEMPTS = int(os.getenv("MAX_REPAIR_RETRIES", "2"))
HTTP_MAX_RETRIES = 4
BACKOFF_BASE_S = 0.5
BACKOFF_CAP_S = 8.0
BACKOFF_JITTER = 0.25  # ±25%
REQUEST_TIMEOUT_S = 30

# --- Input guard ---
NOTE_MAX_CHARS = 12000

# --- Matching thresholds (Plan §7.2, §9.4) ---
FUZZY_MATCH = 90
FUZZY_ADJUDICATE_LOW = 80
ICD_ACCEPT = 90
ICD_ACCEPT_SINGLE = 80
NEGATION_WINDOW = 5  # tokens

# --- Caching ---
ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() == "true"
# When True, a cache miss raises instead of calling the network. Set at runtime
# by `run_eval.py --from-cache` to guarantee zero network calls (Plan F3/DoD-13).
CACHE_ONLY = os.getenv("CACHE_ONLY", "false").lower() == "true"

# --- CORS ---
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

# --- Feature flags ---
ENABLE_ICD10 = os.getenv("ENABLE_ICD10", "true").lower() == "true"
# "mcp" -> spawn the icd10_mcp server; "function" -> in-process function calling.
ICD10_MODE = os.getenv("ICD10_MODE", "mcp").lower()

# Valid prompt versions the /extract endpoint accepts via ?version=.
PROMPT_VERSIONS = ("v1", "v2", "v3", "final")
DEFAULT_VERSION = "final"

# The urgency field is a closed vocabulary.
URGENCY_LEVELS = ("low", "medium", "high")


def resolved_model(fast: bool = False) -> str:
    """The model id in effect for the active provider."""
    if PROVIDER == "ollama":
        return MODEL_LOCAL
    return MODEL_ITER if fast else MODEL_PRIMARY


def provider_configured() -> bool:
    """Whether the active provider has the credentials it needs."""
    if PROVIDER == "ollama":
        return True  # local, no key
    return bool(GROQ_API_KEY)
