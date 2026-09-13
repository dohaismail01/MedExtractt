# MedExtract

Clinical note -> validated structured JSON + ICD-10 candidate codes. Built to the
contract in [CLAUDE.md](CLAUDE.md) (design rationale in [approach.md](approach.md)).

Turns a free-text clinical note into a validated object — chief complaint,
symptoms, diagnoses, history, medications, procedures, follow-up, a grounded
summary, documentation-based risk/urgency, and candidate ICD-10 codes. Every
fact carries an `evidence` span with character offsets so it can be checked
against the note.

> **ICD-10 codes are suggestions for clinician review, not final coding.
> Risk/urgency reflect language in the note, not a triage judgement.**

## Quick start

The package lives under `src/` (src layout). Install it editable so `medextract`
imports everywhere, then run:

```bash
pip install -e .                 # installs medextract (from src/) + deps
python -m pytest                 # tests (pytest adds src/ to the path)
python -m eval.run_eval          # metrics -> eval/reports/
uvicorn medextract.api.app:app --reload   # http://127.0.0.1:8000/docs
```

```bash
curl -s http://127.0.0.1:8000/extract \
  -H 'Content-Type: application/json' \
  -d '{"note": "Severe chest pain radiating to the arm. Denies SOB. Hx hypertension. Dx acute MI."}'
```

## No LLM required

By default the `stub` provider (a deterministic offline extractor) runs the
whole pipeline and test-suite with no API key. Switch to a real model by setting
env vars — the client is an adapter, so pipeline code is untouched:

```bash
MEDEXTRACT_LLM_PROVIDER=ollama   MEDEXTRACT_MODEL=llama3.3
# or
MEDEXTRACT_LLM_PROVIDER=openai_compat  MEDEXTRACT_MODEL=... \
  MEDEXTRACT_LLM_BASE_URL=https://api.example.com/v1  MEDEXTRACT_LLM_API_KEY=...
```

See [.env.example](.env.example) for all settings (CLAUDE.md §8).

## Layout

```
medextract/
  schemas.py          # single source of truth (Pydantic v2)
  config.py           # pydantic-settings, env-driven
  prompts/            # versioned .md prompts + loader
  llm/                # LLMClient protocol + stub / ollama / openai_compat
  pipeline/           # extract, validate (grounding), repair, summary, risk
  icd10/              # source (SQLite FTS) + tools + bounded agent
  api/                # FastAPI app factory + routes
  orchestrator.py     # wires the full pipeline
  safety.py           # PHI redaction, validation, disclaimer
eval/                 # datasets/, metrics.py, run_eval.py, reports/
tests/                # mirror the package
```

## Pipeline

```
note -> validate/redact -> extract (LLM or stub) -> validate + repair
     -> icd10 agent + grounded summary + risk/urgency -> MedExtractResponse
```

- **Evidence grounding:** each span is located in the note (offsets recorded);
  unsupported facts are dropped and counted, fuzzy near-misses accepted via
  rapidfuzz. Structural failures trigger bounded repair; grounding failures are
  silent quality signals.
- **ICD-10 agent:** operates only on validated terms, uses named tools
  (`search_codes`/`lookup_code`/`validate_code`/`get_category`), bounded to 5
  calls/term and 25/note, records a `resolution_path`, abstains below the
  confidence threshold. Procedures are left uncoded (no PCS source).

## Safety / privacy / security

- PHI/PII redaction utility + `/redact` endpoint; raw notes never logged.
- Optional API-key auth (`MEDEXTRACT_API_KEY`), configurable CORS, 50 KB body cap.
- Every `/extract` response carries a disclaimer; the pipeline adds no clinical facts downstream.

See [HANDOFF.md](HANDOFF.md) for status and next steps.

## Disclaimer

Research/educational prototype. Not fit for clinical deployment without
additional safety, privacy, security, and validation work.
