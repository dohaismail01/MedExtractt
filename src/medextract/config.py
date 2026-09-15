"""Env-driven configuration (SPEC.md §8) via pydantic-settings.

All values have defaults so the system runs with zero configuration (using the
deterministic ``stub`` LLM provider, which keeps tests offline). Set a real
provider/model to switch to an instruction-tuned LLM without touching pipeline
code (the client is an adapter).
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # --- LLM ---
    # "stub" -> deterministic offline extractor (default; keeps tests hermetic)
    llm_provider: Literal["stub", "ollama", "openai_compat"] = Field(
        default="stub", alias="MEDEXTRACT_LLM_PROVIDER"
    )
    model: str = Field(default="stub-heuristic", alias="MEDEXTRACT_MODEL")
    llm_base_url: str = Field(default="", alias="MEDEXTRACT_LLM_BASE_URL")
    llm_api_key: str = Field(default="", alias="MEDEXTRACT_LLM_API_KEY")
    llm_timeout_s: float = Field(default=30.0, alias="MEDEXTRACT_LLM_TIMEOUT")
    # Output-token budget. Reasoning models (e.g. gpt-oss) spend heavily on hidden
    # reasoning; without headroom the JSON `content` can come back empty on long
    # notes. Keep this generous.
    llm_max_tokens: int = Field(default=8192, alias="MEDEXTRACT_LLM_MAX_TOKENS")
    # Transient-error resilience: retry on HTTP 429 (rate limit) and 5xx with
    # backoff, honoring a Retry-After header when the provider sends one. Groq's
    # free tier has a low tokens-per-minute cap, so a batch eval hits 429 often.
    llm_max_retries: int = Field(default=4, alias="MEDEXTRACT_LLM_MAX_RETRIES")
    llm_retry_base_delay: float = Field(default=2.0, alias="MEDEXTRACT_LLM_RETRY_BASE_DELAY")
    llm_retry_max_delay: float = Field(default=30.0, alias="MEDEXTRACT_LLM_RETRY_MAX_DELAY")

    # --- Prompts / pipeline ---
    prompt_version: str = Field(default="final", alias="MEDEXTRACT_PROMPT_VERSION")
    max_repair_attempts: int = Field(default=2, alias="MAX_REPAIR_ATTEMPTS")
    fuzzy_grounding_threshold: int = Field(default=90, alias="FUZZY_GROUNDING_THRESHOLD")
    # Evidence *coherence* (validate.py Layer B, step 2): the fraction of a fact's
    # content tokens that must be supported by its evidence span. Locating the
    # span in the note is necessary but not sufficient — the evidence must also
    # actually mention the extracted fact, or the fact is conservatively dropped.
    coherence_min_coverage: float = Field(default=0.5, alias="COHERENCE_MIN_COVERAGE")
    coherence_token_fuzz: int = Field(default=85, alias="COHERENCE_TOKEN_FUZZ")

    # --- ICD-10 agent ---
    max_icd10_tool_calls_per_term: int = Field(
        default=5, alias="MAX_ICD10_TOOL_CALLS_PER_TERM"
    )
    max_icd10_tool_calls_per_note: int = Field(
        default=25, alias="MAX_ICD10_TOOL_CALLS_PER_NOTE"
    )
    icd10_confidence_threshold: float = Field(
        default=0.6, alias="ICD10_CONFIDENCE_THRESHOLD"
    )
    icd10_accept_threshold: float = Field(default=0.8, alias="ICD10_ACCEPT_THRESHOLD")
    # The ICD-10 agent is online-only (NLM Clinical Table Search Service); there is
    # no local backend or fallback. Kept as a field for /health visibility.
    icd10_backend: Literal["nlm", "online"] = Field(
        default="nlm", alias="ICD10_BACKEND"
    )

    # --- Safety / privacy / security (SPEC.md §0 rule 6, §5) ---
    max_note_bytes: int = Field(default=50_000, alias="MEDEXTRACT_MAX_NOTE_BYTES")
    api_key: str = Field(default="", alias="MEDEXTRACT_API_KEY")
    allowed_origins: str = Field(default="*", alias="MEDEXTRACT_ALLOWED_ORIGINS")
    redact_input: bool = Field(default=False, alias="MEDEXTRACT_REDACT_INPUT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "stub"

    @property
    def cors_origins(self) -> List[str]:
        raw = self.allowed_origins.strip()
        if raw in ("", "*"):
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
