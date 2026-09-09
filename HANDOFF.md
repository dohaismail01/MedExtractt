# MedExtract AI - Build Handoff Log

A running, incremental record of what was built and why. Newest entries at the
bottom of the log. This file is updated every time a meaningful step is taken.

Repo: https://github.com/dohaismail01/MedExtract

---

## Current status (snapshot)

- **Backend:** complete and aligned to `docs/MedExtract_AI_Project_Plan.md`. Two-call
  pipeline, strict Pydantic schema + repair loop, prompts V1->Final, provenance,
  FHIR export, eval harness, ICD-10 via MCP server **and** function-calling fallback.
- **Tests:** 20 passing offline (`python -m pytest -q`).
- **MCP server:** `icd10_mcp` spawns over stdio and answers; `/health` shows
  `mcp_reachable: true`.
- **Frontend:** in progress (Vite + React + TS + Tailwind scaffold started).
- **Blocking for live runs:** real `GROQ_API_KEY` must be placed in `.env`
  (currently a placeholder -> 401).

---

## Environment

- Python 3.11.9 in a project venv at `.venv/` (isolated from the host).
- Node v24 / npm 11 for the frontend.
- Install backend deps: `.venv/Scripts/python -m pip install -r requirements.txt`

---

## Step log

### 1. Read the spec
- Read `docs/MedExtract_AI_Project_Proposal.md` and `..._Project_Plan.md`
  (moved into `docs/`). These define the approach and the detailed build spec.

### 2. Backend scaffold + core modules
- `requirements.txt`, `.env.example`, `.gitignore`, project folders.
- `app/config.py` - all constants (models, decoding params, thresholds, cache).
- `app/schema.py` - Medication / Extraction / Assessment / MedExtractResult
  (strict, `extra="forbid"`; 10-field public contract).
- `app/llm_client.py` - OpenAI-compatible wrapper (Groq/Ollama), retry+backoff
  on 429/5xx, on-disk response cache, JSON parsing.

### 3. Prompts
- `prompts/v1..final.txt` (failure-driven versions), `narrative.txt` (Call 2),
  `repair.txt` (repair template), `CHANGELOG.md`. Anti-injection rule added in
  V3/Final (text in <note> is data, not instruction).

### 4. Pipeline
- `app/extract.py` - two-call pipeline + `call_with_repair` loop; Call 2 gets
  the validated JSON only, never the note. Emits status ok/repaired/exhausted.
- `app/provenance.py` - locates items in the note; negation-aware grounding.
- `app/normalise.py` - normalise() / matches() (rapidfuzz) / in_negation_scope().
- `app/fhir_export.py` - FHIR R4 Bundle mapping.

### 5. ICD-10 (both paths)
- `mcp_servers/icd10_mcp/` - standalone FastMCP server (stdio): `server.py`,
  `nlm.py` (NLM API), `cms_fallback.py` (offline CSV), accept rule + audit log.
- `app/mcp_client.py` - FastAPI-side MCP client (spawns server, discovers tools,
  routes one lookup per diagnosis). Forces child UTF-8 to fix a Windows stdio bug.
- `app/icd10_tool.py` - in-process function-calling fallback.
- Note: tool `annotations` dropped (pinned mcp==1.2.0 rejects the kwarg).

### 6. API
- `app/api.py` - `/extract` (+ `?version`, `?format=fhir`, `provenance` flag),
  `/health`, `/eval/results`, CORS. Diagnostics in response headers
  (X-Validation-Status / X-Repair-Attempts / X-Model-Id); body stays 10 fields.

### 7. Evaluation + data
- `eval/gold_set.jsonl` (15 hand-labeled), `adversarial.jsonl` (7, C1-C8),
  `scratch_set.jsonl` (10), `aliases.jsonl`.
- `eval/run_eval.py` - per-version metrics, `--from-cache` (zero network).
- `reference/icd10cm_codes.csv` - offline ICD-10 fallback sample.

### 8. Data loader
- `scripts/download_data.py` (Kaggle dataset -> ./data), `scripts/sample_notes.py`.
- Finding: the Kaggle dataset is depression-screening classification data, not
  rich clinical notes; eval runs on the hand-labeled gold set instead.

### 9. Tests + config
- `tests/` - schema, repair, normalise, negation, provenance;
  `mcp_servers/icd10_mcp/tests/` - accept rule. `pytest.ini`. 20 passing.
- `Makefile`, root `README.md`.

### 10. Docs housekeeping (user requests)
- Removed `docs/MedExtract_AI_Overview.md`.
- Gitignored `docs/MedExtract_AI_Project_Plan.md` (kept local, not published).
- Fixed README encoding (was accidentally UTF-16 -> now clean UTF-8).
- Created this `HANDOFF.md`.

### 11. Frontend (in progress)
- `frontend/` scaffold: `package.json`, `vite.config.ts` (proxies /api -> :8000),
  `tsconfig*.json`. Components and screens next.

### 12. First push to GitHub
- Committed backend + eval + MCP server + frontend scaffold and pushed to
  `origin/main`. Verified ignores: `.env`, the internal Plan, `.venv/`, `data/`,
  `eval/cache/`, `frontend/node_modules/` all excluded; only the placeholder
  `.env.example` is published.

### 13. No-synthetic-data (user constraint)
- Rebuilt all eval sets from REAL rows of the Kaggle dataset (no fabricated
  notes): `gold_set.jsonl` (15), `adversarial.jsonl` (6), `scratch_set.jsonl`
  (10). Gold/adversarial pair each real note with hand-added labels.
- Adversarial notes are real mood-text rows; the guardrail assertion is that the
  system must NOT invent a diagnosis/medication from them (diagnosis stays []).
- Scrubbed "synthetic" wording from the Proposal, Plan, README, and
  download_data.py, keeping the no-PII assurance.

### 14. Docs housekeeping (round 2)
- README: added an "Implementation notes (deviations from the original spec)"
  section (both ICD-10 paths, real eval data, dropped MCP annotations, plain-dict
  FHIR, Windows stdio fix) and updated the Data section.
- Fixed README that had been saved as UTF-16 -> now UTF-8.

### 15. Attribution (user request)
- Removed the "Co-Authored-By: Claude" trailer from the commit and omit it going
  forward, so Claude does not appear in the GitHub contributor list.

### 16. Frontend complete (Phase 4)
- Full Vite + React + TS + Tailwind app under `frontend/`:
  - `api.ts` (fetch wrapper, reads X-* headers), `types.ts` (mirror of the
    10-field contract), `App.tsx` (Extract / Compare / Evaluate tabs + health
    banner).
  - Components: NoteInput (textarea + .txt upload + sample + version picker),
    ResultPanel (10 field cards; empties shown as "not stated in note"),
    MedicationTable, UrgencyBadge, HighlightedNote (provenance <mark> spans +
    ungrounded warnings), VersionCompare (V1->Final side by side), EvalTable.
  - Vite dev proxies /api -> :8000 (no CORS needed in dev).
- `npm run build` passes (tsc type-check + Vite bundle). UI verified rendering
  in the browser (all three tabs).

## Next steps
- Add a real GROQ_API_KEY to `.env`, then run one live `/extract` and the eval
  sweep (`python -m eval.run_eval`) to populate the V1->Final table.
- Optional: run backend (:8000) + frontend (:5173) together for a full demo.
