# MedExtract — Handoff Log

Running log of work done on this repo. Newest entries are appended at the
bottom. Each entry is numbered; increment on every change.

## Current status (snapshot)

- **What it is:** clinical note → validated structured JSON + ICD-10 candidate
  codes + grounded summary + documentation-based risk/urgency + FastAPI.
- **Contract:** built to [CLAUDE.md](CLAUDE.md) (design rationale in
  [approach.md](approach.md)). Package layout, data contracts, pipeline stages,
  agent bounds, API shape, and eval metrics all follow that spec.
- **Runs with zero config:** default `stub` LLM provider is a deterministic
  offline extractor, so the pipeline and tests run with no API key. Set
  `MEDEXTRACT_LLM_PROVIDER=ollama|openai_compat` (+ model) for a real LLM.
- **Tests:** 53 passing (`python -m pytest`).
- **Baseline eval** (stub, 5-note gold set): extraction F1 0.973, ICD-10 top-1
  1.0, invalid-code 0.0, urgency 1.0 — recorded in `eval/reports/baseline.md`.
  *Optimistic: gold set overlaps the stub lexicon; smoke test only.*

## How to run

```bash
pip install -r requirements.txt
python -m pytest
python -m eval.run_eval
uvicorn medextract.api.app:app --reload    # http://127.0.0.1:8000/docs
```

## Architecture (as built, matches CLAUDE.md §1)

```
medextract/
  schemas.py          source of truth (strict internal + flat LLM-facing models)
  config.py           pydantic-settings, env-driven
  prompts/            extraction_v1/v2.md, repair.md, summary.md + loader
  llm/                LLMClient protocol; stub / ollama / openai_compat
  pipeline/           extract, validate (grounding+offsets), repair, summary, risk
  icd10/              source (SQLite FTS + rapidfuzz), tools, bounded agent
  api/                app factory + routes (/extract /health /redact)
  orchestrator.py     wires the pipeline, builds RunMeta
  safety.py           PHI redaction, note validation, disclaimer
eval/                 datasets/, metrics.py, run_eval.py, reports/baseline.md
tests/                mirror the package (schemas, validate, repair, risk/summary,
                      icd10, safety, orchestrator+api)
```

## Not yet done / next steps

- Prompt V2 is written but not yet evaluated head-to-head vs V1 on the same set.
- Real-LLM run + a larger held-out gold set that does NOT overlap the stub lexicon.
- `mcp` ICD-10 backend and ICD-10-PCS procedure coding (procedures abstain today).
- Ablation flags (llm_only → +validation → +repair → +icd10) — config seams exist.
- React demo UI (optional, CLAUDE.md §7 step 9).
- `mypy --strict` pass (config in pyproject.toml; not yet run clean).

---

## Change log

1. **Assessed repo state.** Only `README.md` + `approach.md` on disk; a full prior
   implementation sat in `HEAD` but was deleted from the working tree. User chose
   **build fresh from scratch**.
2–11. **First build (flat `app/` package).** Schema, config, prompts, LLM client,
   offline extractor, extraction+validate+repair, ICD-10 CSV + agent, summary/risk,
   pipeline, FastAPI, tests + eval, README + this handoff. 37 tests passing.
12. **Fixed README encoding** (was UTF-16 → rewrote as UTF-8).
13. **Safety/privacy/security layer** added to the `app/` build: `safety.py`
    (PHI redaction, note validation, disclaimer), config for API-key/CORS/limits,
    `/redact` endpoint, PHI-safe logging, disclaimer in responses; tests (49 total).
14. **User supplied `CLAUDE.md`** (stricter build contract); saved to repo root.
    User chose **Option 1: full refactor to spec**.
15. **Refactored to `medextract/` package** per CLAUDE.md §1: sub-packages
    `llm/ pipeline/ icd10/ api/ prompts/`, `orchestrator.py`, `safety.py`.
16. **Matched data contracts** (§2): `Evidence{text,start,end}`, `RiskIndicator`,
    urgency `routine/elevated/urgent`, `ICD10Suggestion{source_term,code_system}`,
    strict `RunMeta`; flat LLM-facing models lifted by the validator.
17. **Rebuilt stages:** LLM adapter (stub/ollama/openai_compat, JSON mode),
    validation with offset grounding + rapidfuzz fuzzy fallback, bounded repair
    (`ExtractionFailed` after limit), deterministic grounded summary, risk with a
    data-file lexicon + auditable urgency rule table.
18. **Rebuilt ICD-10 agent (§4):** SQLite-FTS source adapter, named tool wrappers,
    bounded loop (5/term, 25/note), `resolution_path` in spec format
    (`search:…`, `broaden:…`, `validate:CODE:ok`, `accept`/`abstain`,
    `pcs_unsupported`), 0.6 abstain / 0.8 accept thresholds.
19. **Eval + docs:** `eval/metrics.py` + `run_eval.py` (P/R/F1, schema validity,
    repair rate, ICD-10 top-1/abstention/invalid, p50/p95 latency, tool calls);
    committed `eval/reports/baseline.md`; `pyproject.toml`; updated requirements,
    `.env.example`, `.gitignore`, README. Removed old `app/`, `.txt` prompts, old
    tests. **53 tests passing.**
20. **Cleanup + rename + code-review fixes (this session).**
    - Removed gitignored cruft: `__pycache__/`, `.pytest_cache/`, generated
      `eval/reports/eval_*.{json,md}` (kept only `baseline.md`).
    - **Renamed the Python package `clinextract` → `medextract`** in all three
      case forms (`clinextract`→`medextract`, `ClinExtract`→`MedExtract`,
      `CLINEXTRACT`→`MEDEXTRACT`): directory + 23 files (source, tests, eval,
      pyproject, README, `.env.example`, CLAUDE.md, this handoff). Env prefix is
      now `MEDEXTRACT_*`; repo-root folder is still `MEDExtract`.
    - Ran `/code-review` (medium) of `medextract/` vs CLAUDE.md; **fixed 6
      findings:** (1) grounding now stores the verbatim note substring, not the
      LLM span (§0 rule 2); (2) summary capped to 4 sentences (§3.4); (3) API
      note-size cap unified on `settings.max_note_bytes` (dropped the duplicate
      hardcoded 50 KB); (4) `_CODEABLE` status filter now applies to PCS too, so
      negated/family procedures aren't coded; (5) ICD-10 `resolution_path` no
      longer logs `broaden:*` steps that never ran (guarded by `can_call()`);
      (6) removed dead `aliases` local in `icd10/source.py`.
    - **Still 53 tests passing**; end-to-end smoke clean.
    - **NOT COMMITTED:** entries 15–20 (the whole `medextract/` refactor, the
      rename, and these fixes) are uncommitted in the working tree on top of the
      `app/` deletions. Commit a checkpoint before further work.
21. **Rebuilt the React frontend (`frontend/`, this session).** Vite + React 18
    + TypeScript + Tailwind, matching the current `MedExtractResponse` shape.
    `src/types.ts` mirrors `schemas.py`; `src/api.ts` calls `POST /extract`
    (base URL via `VITE_API_URL`, default `http://127.0.0.1:8000`). Components:
    NoteInput (in `App.tsx`), HighlightedNote (evidence + risk spans via
    start/end offsets), FactList (status pills), MedicationTable, Icd10Panel
    (confidence bar + expandable `resolution_path`), UrgencyBadge, MetaBar.
    Run: `uvicorn medextract.api.app:app --reload` then `cd frontend && npm
    install && npm run dev`. **Not yet `npm install`ed / run in this session**
    (no network install performed); also uncommitted. Replaces the old deleted
    `frontend/` (CLAUDE.md §7 step 9, previously "not done").
