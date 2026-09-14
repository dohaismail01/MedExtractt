# MedExtract — Technical Specification 

Clinical note → validated structured JSON + ICD-10 candidate codes.
This file is the build contract. Read it before writing code; keep it updated when decisions change.

---

## 0. Non-Negotiable Rules

These are enforced by code, not by prompt alone. Violating any of them is a bug.

1. **Extraction is closed-world.** Only facts explicitly present in the note. No inference, no diagnosis, no treatment advice.
2. **Every clinical fact carries `evidence`** — a verbatim substring of the input note. If a span is not found in the note (after normalization), the fact is dropped and counted as `unsupported`.
3. **Downstream stages never add clinical facts.** The ICD-10 agent, summary generator, and risk flagger read *validated structured data only* — never the raw note.
4. **ICD-10 output is a suggestion.** Every code carries `confidence` and `needs_review`. Low confidence → `code: null`, `needs_review: true`. Never guess to fill the field.
5. **Risk/urgency is documentation-based**, derived from language in the note. It is not triage. Label it as such in every output surface.
6. **No PHI leaves the process** beyond the configured LLM endpoint. No logging of raw note text at INFO level or above.

---

## 1. Repository Layout

```
medextract/
├── medextract/
│   ├── __init__.py
│   ├── config.py              # pydantic-settings; env-driven
│   ├── schemas.py             # Pydantic models (single source of truth)
│   ├── prompts/
│   │   ├── __init__.py        # loader: get_prompt(name, version)
│   │   ├── extraction_v1.md
│   │   ├── extraction_v2.md
│   │   ├── repair.md
│   │   └── summary.md
│   ├── llm/
│   │   ├── base.py            # LLMClient protocol
│   │   ├── openai_compat.py   # OpenAI-compatible (Groq/Together/vLLM)
│   │   └── ollama.py
│   ├── pipeline/
│   │   ├── extract.py         # stage 1
│   │   ├── validate.py        # stage 2: schema + evidence grounding
│   │   ├── repair.py          # stage 3: bounded retry
│   │   ├── summary.py         # stage 5: grounded summary
│   │   └── risk.py            # stage 5: documentation-based flags
│   ├── icd10/
│   │   ├── agent.py           # bounded tool-calling loop
│   │   ├── tools.py           # search / lookup / validate tool defs
│   │   └── source.py          # ICD-10 data backend adapter
│   ├── api/
│   │   ├── app.py             # FastAPI app factory
│   │   └── routes.py
│   └── orchestrator.py        # wires the full pipeline
├── eval/
│   ├── datasets/              # notes + gold annotations (gitignored if real)
│   ├── run_eval.py
│   ├── metrics.py
│   └── reports/
├── tests/
├── pyproject.toml
└── README.md
```

---

## 2. Data Contracts (`schemas.py`)

Pydantic v2. These models are the interface between every stage — no dicts crossing module boundaries.

```python
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field

class Status(str, Enum):
    PRESENT        = "present"
    NEGATED        = "negated"
    HISTORICAL     = "historical"
    FAMILY_HISTORY = "family_history"
    UNCERTAIN      = "uncertain"

class Evidence(BaseModel):
    text: str                       # verbatim span from the note
    start: int | None = None        # filled by validator, not the LLM
    end: int | None = None

class ClinicalFact(BaseModel):
    text: str
    status: Status = Status.PRESENT
    evidence: Evidence

class Medication(BaseModel):
    name: str
    dose: str | None = None
    frequency: str | None = None
    duration: str | None = None
    evidence: Evidence

class ICD10Suggestion(BaseModel):
    source_term: str                # the validated diagnosis/procedure text
    code: str | None                # None when confidence insufficient
    description: str | None = None
    code_system: Literal["ICD-10-CM", "ICD-10-PCS"] | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    needs_review: bool
    resolution_path: list[str] = []  # audit trail of agent steps

class RiskIndicator(BaseModel):
    term: str                        # e.g. "severe", "radiating"
    evidence: Evidence

class ExtractionResult(BaseModel):
    chief_complaint: ClinicalFact | None = None
    symptoms: list[ClinicalFact] = []
    diagnosis: list[ClinicalFact] = []
    medical_history: list[ClinicalFact] = []
    medications: list[Medication] = []
    procedures: list[ClinicalFact] = []
    follow_up: str | None = None

class MedExtractResponse(ExtractionResult):
    summary: str | None = None
    risk_indicators: list[RiskIndicator] = []
    urgency: Literal["routine", "elevated", "urgent"] | None = None
    icd10_codes: list[ICD10Suggestion] = []
    meta: "RunMeta"

class RunMeta(BaseModel):
    prompt_version: str
    model: str
    repair_attempts: int
    unsupported_dropped: int
    icd10_tool_calls: int
    latency_ms: int
```

**Conventions:** missing scalar → `null`; missing list → `[]`. Never omit a key.

The LLM is asked for a *flatter* shape (evidence as a plain string). `validate.py` lifts it into `Evidence` with offsets. Keep the LLM-facing schema simple; keep the internal schema strict.

---

## 3. Pipeline

```
note ─▶ extract ─▶ validate ─┬─(fail)─▶ repair ─▶ validate ─┬─(fail x N)─▶ error
                             │                              │
                             └──────── validated ◀──────────┘
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                    icd10 agent      summary          risk flags
                          └───────────────┼───────────────┘
                                          ▼
                                  MedExtractResponse
```

### 3.1 `extract.py`
- One LLM call. Temperature 0. JSON-mode / structured output where the provider supports it.
- Prompt = `prompts/extraction_{version}.md` + the note. Version comes from config, never hardcoded at the call site.
- Returns raw text; parsing is the validator's job.

### 3.2 `validate.py` — two layers

**Layer A — structural.** Parse JSON, coerce through Pydantic. On failure, collect a compact error list (`loc: msg`) for the repair prompt.

**Layer B — evidence grounding.** For each fact:
1. Normalize note and span (lowercase, collapse whitespace, strip punctuation runs).
2. Exact substring match → record `start`/`end` into the original note's index space.
3. If no exact match, try a fuzzy match (`rapidfuzz.partial_ratio ≥ 90`). Accept but mark in meta.
4. Otherwise **drop the fact**, increment `unsupported_dropped`, and log the term (not the note).

Grounding failures do **not** trigger repair — they are silent quality signals measured in eval. Only structural failures trigger repair.

### 3.3 `repair.py`
- Max attempts: `MAX_REPAIR_ATTEMPTS` (default **2**).
- Repair prompt receives: the schema, the invalid output, the error list. Not a re-run of extraction — a correction task.
- After the limit, raise `ExtractionFailed`; the API returns 422 with the error list. Never return a partially-guessed object.

### 3.4 `summary.py`
- Input: the validated `ExtractionResult` serialized as JSON. **The raw note is not passed.**
- Output: 2–4 sentences. Must not introduce any term absent from the structured data — assert this with a token-overlap check in tests.

### 3.5 `risk.py`
- Deterministic, no LLM. A curated lexicon of intensity/acuity/radiation terms matched against evidence spans of `status == present` facts.
- `urgency` derives from a documented rule table (count and category of matched terms). Rules live in one dict in this module so they are auditable and testable.
- Ship the lexicon as a data file, not inline strings.

---

## 4. ICD-10 Agent (`icd10/agent.py`)

Agentic in a narrow, defensible sense: it makes **bounded search decisions** to resolve an already-validated term. It cannot create clinical facts.

**Inputs:** validated `diagnosis` (→ ICD-10-CM) and `procedures` (→ ICD-10-PCS *only if the backend supports PCS*; otherwise leave uncoded with `needs_review: true` and a `resolution_path` entry `"pcs_unsupported"`).

**Tools exposed to the loop:**

| Tool | Signature | Purpose |
|---|---|---|
| `search_codes` | `(query: str, code_type, search_by="description")` | primary lookup |
| `lookup_code` | `(code: str)` | full detail for a candidate |
| `validate_code` | `(code: str)` | validity + billability check |
| `get_category` | `(code: str)` | hierarchy / sibling exploration |

**Loop:**

```
term
 └─ search_codes(term)
     ├─ single strong match ─▶ validate_code ─▶ accept (confidence ≥ 0.8)
     ├─ multiple plausible  ─▶ lookup_code on top-k ─▶ pick or escalate
     └─ none / weak         ─▶ broaden: drop modifiers, expand abbreviation,
                               get_category on nearest ancestor
                               └─ retry once ─▶ validate or abstain
```

**Bounds:** `MAX_ICD10_TOOL_CALLS_PER_TERM = 5`, hard ceiling per note = 25. On exhaustion → abstain.

**Abstention rule:** confidence < `ICD10_CONFIDENCE_THRESHOLD` (default 0.6) → `code: null`, `needs_review: true`. Abstention is a success mode, not a failure.

**`resolution_path`** records each step as a short string (`"search:chest pain"`, `"broaden:drop_modifier"`, `"validate:R07.9:ok"`). Required for the eval harness.

**Backend (`icd10/source.py`)** is an adapter with one interface. Implementations: the MCP ICD-10 server when available, otherwise a local ICD-10-CM tabular file loaded into SQLite FTS. The agent must not know which is in use.

---

## 5. API (`api/routes.py`)

```
POST /extract
  body: { "note": str, "include_icd10": bool = true, "include_summary": bool = true }
  200:  brief flat schema (see below)
  422:  { "error": "validation_failed", "details": [...] }
  504:  { "error": "llm_timeout" }

GET  /health   → { status, model, prompt_version, disclaimer, ... }
```

**Output contract (decision, 2026-09):** the `/extract` response conforms to the
project brief's **exact flat schema**, not the rich internal `MedExtractResponse`.
`medextract/brief.py` (`to_brief`) is the single place that flattens the rich
model to it: `chief_complaint` → string; `symptoms`/`diagnosis`/`medical_history`/
`procedures`/`risk_indicators` → string arrays; `medications` →
`{name,dose,frequency,duration}`; `urgency` → `low|medium|high` (mapped from the
internal routine/elevated/urgent); plus the bonus `icd10_codes` list mapping each
diagnosis to a code (or null). Negated/family-history facts are dropped from the
affirmative arrays. The rich models (evidence offsets, `status`, `meta`) remain
the **internal** representation used by grounding and the eval harness — they are
not emitted by the API.

- Request body size cap: 50 KB (from `MEDEXTRACT_MAX_NOTE_BYTES`).
- Per-request timeout: 90 s total; per-LLM-call 30 s.
- Safety disclaimer (`"Suggestions for clinician review. Not a diagnostic or
  triage tool."`) is surfaced via `GET /health` and the UI, keeping the
  `/extract` body exactly the brief schema.

---

## 6. Evaluation (`eval/`)

Offline, on a held-out annotated set. `run_eval.py` takes `--prompt-version`, `--config`, `--limit` and writes a timestamped JSON + Markdown report to `eval/reports/`.

**Extraction metrics** — per field and micro-averaged:
- Precision / Recall / F1 (match = normalized text equality + correct `status`)
- Unsupported extraction rate (facts dropped at grounding)
- Schema validity rate (first pass)
- Repair rate and post-repair validity

**ICD-10 metrics:**
- Top-1 accuracy (against gold code, on terms where gold exists)
- Candidate recall @k
- Abstention rate, and **abstention precision** (was abstaining correct?)
- Invalid-code rate (should be 0 — validated codes only)

**System:** p50/p95 latency per note, mean tool calls per term.

**Prompt iteration:** V1 → evaluate → categorize failures → V2/V3 → final. Every version runs on the *same* subset; the report table is append-only so regressions are visible.

**Ablation (optional):** `llm_only` → `+validation` → `+repair` → `+icd10_agent`, toggled by config flags so one code path serves all four.

---

## 7. Build Order

Implement and verify in this order. Do not skip ahead — step 3 sets the reference numbers everything else is judged against.

1. `schemas.py` + `config.py` + LLM client adapter. Tests for schema round-trip.
2. `extract.py` + prompt V1 + `validate.py` (both layers) + `repair.py`.
3. **Evaluate baseline.** Record metrics in `eval/reports/baseline.md` before adding anything.
4. Prompt V2/V3; re-evaluate on the identical subset.
5. `icd10/` — source adapter, tools, agent. Evaluate the agent in isolation against gold terms.
6. `summary.py` + `risk.py` with the no-new-facts assertion test.
7. FastAPI integration.
8. Full-system evaluation + report.
9. Optional demo UI.

---

## 8. Stack & Configuration

- Python 3.11+, FastAPI, Pydantic v2, pydantic-settings, httpx, rapidfuzz, pytest.
- LLM candidates: Llama 3.3 70B, Qwen 2.5 72B, or a smaller local model via Ollama. Selection criteria: extraction quality, structured-output reliability, latency, cost/rate limits. **The client is an adapter — swapping models must not touch pipeline code.**
- Agent: custom tool-calling loop (no framework dependency) so the bounds and audit trail stay explicit.

Config via env, all with defaults in `config.py`:

```
MEDEXTRACT_LLM_PROVIDER=ollama|openai_compat
MEDEXTRACT_MODEL=...
MEDEXTRACT_PROMPT_VERSION=v1
MAX_REPAIR_ATTEMPTS=2
MAX_ICD10_TOOL_CALLS_PER_TERM=5
ICD10_CONFIDENCE_THRESHOLD=0.6
ICD10_BACKEND=mcp|local_sqlite
LOG_LEVEL=INFO
```

---

## 9. Coding Conventions

- Type hints everywhere; `mypy --strict` on `medextract/`.
- Each pipeline stage is a pure function `(input_model, deps) -> output_model`. No hidden state, no module-level clients.
- LLM calls only inside `llm/` and the stage that owns them. Never inside `validate.py`, `risk.py`, or `icd10/tools.py`.
- Prompts live in `.md` files, never in Python string literals. Versioned by filename; deleting a version is forbidden while a report references it.
- Logging: structured, `note_id` only. Raw note text at DEBUG only, never in eval reports checked into git.
- Tests mirror the package layout. Every stage needs a fixture-driven test with a golden output.

---

## 10. Known Risks

- Public/synthetic notes may not reflect real clinical variability — state this next to any metric.
- Grounding reduces but does not eliminate hallucination; the unsupported-extraction rate is the honest measure of what remains.
- Negation, uncertainty, and abbreviation are the expected failure modes. Build targeted test cases for each before tuning prompts broadly.
- A clinical term often maps to several plausible codes; measure candidate recall, not only top-1.
- Not fit for clinical deployment without additional safety, privacy, security, and validation work. Do not soften this language anywhere in the repo.
