# MedExtract AI

**Clinical Notes -> Structured Medical Information**
Prompt Engineering | Structured Output | LLM Evaluation

MedExtract AI turns an unstructured clinical note into a fixed, validated
10-field JSON object. A FastAPI backend runs a two-call prompt pipeline,
validates the output against a strict Pydantic schema (with a repair loop), and
returns structured data. The defining constraint: it extracts only what the note
already states -- **an empty field is a correct answer.**

See [docs/MedExtract_AI_Project_Proposal.md](docs/MedExtract_AI_Project_Proposal.md)
for the full approach: pipeline design, prompt-engineering strategy, evaluation
methodology, and build phases. (A detailed internal build plan is kept locally
and is not published.)

## Architecture

```
POST /extract { "note": "..." }
  -> Call 1  extraction (7 fields) -> Pydantic validate -> repair loop (max 2)
  -> Call 2  summary / risk / urgency  (validated JSON only -- NOT the note)
  -> Call 3  ICD-10 lookup via MCP server (bonus)
  -> 200  10-field JSON  (+ optional icd10_codes / _provenance)
```

Call 2 never receives the note, so it is *structurally* unable to introduce a
fact the note didn't contain -- the no-hallucination rule becomes a property of
the pipeline, not a request to the model.

## Setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate     POSIX:  source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit .env and add your GROQ_API_KEY
```

> The `.env` in this repo has a placeholder key. `GET /health` will report
> `reachable: false` with a 401 until you paste a real Groq key. The key never
> reaches the frontend -- it lives only in the backend `.env` (gitignored).

## Run

```bash
python -m uvicorn app.api:app --reload --port 8000   # backend on :8000
cd frontend && npm install && npm run dev            # frontend on :5173
```

- `POST /extract` -- body `{ "note": "..." }`; `?version=v1|v2|v3|final`,
  `?format=fhir`, and `{ "provenance": true }` optional. Diagnostics ride in the
  `X-Validation-Status`, `X-Repair-Attempts`, and `X-Model-Id` response headers.
  With >=2 medications, an `interaction_flags` key may be attached.
- `POST /extract/agent` -- an **LLM-planner agent**: the model chooses which
  tools to call (extract → validate → repair → assessment → ICD-10 *only if a
  diagnosis exists* → verify). Returns the 10-field result plus `agent_trace`
  (the ordered decisions), `verification` (grounding of each item), and
  `qc_confidence` (a quality-control score, not a medical one).
- `POST /dataset/label` -- body `{ "note": "..." }`; returns the Kaggle
  classification label (depression / no depression) for an exact dataset-row
  match. Separate from the 10-field extraction on purpose.
- `GET /health` -- provider + MCP reachability, resolved model, feature flags.
- `GET /eval/results` -- the stored V1->Final metrics table.
- Interactive docs at `http://localhost:8000/docs`.

### Frontend pages

- **Extract** -- Clinical Note input -> "Extract Information" -> an *Extraction
  Results* grid (the 7 fields + medications) and an *AI Assessment* block
  (summary / risk indicators / urgency), with a Schema-Validated indicator and
  View/Copy JSON. Empty fields render explicitly ("None stated"). The Kaggle
  **dataset label** is shown in its own card, separate from the extraction.
  An **Agent mode** toggle (default on) uses `/extract/agent` and shows an
  *Agent Activity* panel: the step-by-step tool trace, the verification result,
  and the QC confidence.
- **Evaluation** -- the V1->Final metrics table plus a Failure Analysis section.
- **ICD-10** -- diagnosis -> ICD-10 code -> tool verification for the last note.

## ICD-10 (bonus)

Two paths, selected by `ICD10_MODE` in `.env`:
- `mcp` (default) -- spawns the standalone [`icd10_mcp`](mcp_servers/icd10_mcp/)
  server over stdio; FastAPI is the MCP client. Falls back to function calling
  automatically if the server can't start.
- `function` -- in-process function calling ([`app/icd10_tool.py`](app/icd10_tool.py)).

Run the MCP server standalone (e.g. under MCP Inspector):
```bash
python -m mcp_servers.icd10_mcp.server
```

## Evaluation

```bash
python -m eval.run_eval               # live model calls (cached as it goes)
python -m eval.run_eval --from-cache  # regenerate the table, zero network calls
```

Gold, adversarial, and scratch sets live in [eval/](eval/) and never mix.
Metrics: JSON validity (pre/post repair), per-field precision/recall/F1,
medication name-F1 + sub-field accuracy, negation-aware hallucination rate, and
the adversarial guardrail pass rate.

## Test

```bash
python -m pytest -q
```

## Data

```bash
python -m scripts.download_data     # Kaggle dataset -> ./data (gitignored)
```

The evaluation sets ([eval/](eval/)) are built from **real rows of this Kaggle
dataset** — no fabricated notes. The gold and adversarial sets pair each real
note with hand-added labels (annotations, not invented data); the scratch set is
raw notes used only during prompt iteration. The three splits never mix.

> The dataset is short depression-screening notes rather than rich multi-field
> clinical notes, so most extracted fields are correctly empty and `diagnosis`
> stays `[]` (the guardrail: mood text must not be promoted to a diagnosis).

## Implementation notes (deviations from the original spec)

- **ICD-10 uses both approaches.** A standalone FastMCP server *and* an
  in-process function-calling fallback (`ICD10_MODE` selects; `mcp` falls back to
  `function` automatically). The Overview proposed function calling, the Plan
  proposed MCP — this ships both.
- **Eval data is real, not fabricated.** Gold/adversarial/scratch sets are built
  from real rows of the Kaggle dataset with hand-added labels; no invented notes.
- **MCP tool annotations** (readOnlyHint, etc.) are omitted because the pinned
  `mcp==1.2.0` SDK rejects the `annotations=` kwarg; re-add on a newer SDK.
- **FHIR export** is a dependency-light plain-dict R4 mapping (not `fhir.resources`),
  to avoid library-version fragility. Still a structural mapping, not certified.
- **Drug interaction flags** (§12.3) are implemented as an in-process module
  (RxNorm + a local ONCHigh RxCUI-pair table), not a second MCP tool; status is
  always "flagged for pharmacist review" and nothing stronger.
- **Dataset label** (depression / no depression) is served from its own endpoint
  and shown separately in the UI -- it is a classification target, never one of
  the 10 extraction fields.
- **Windows stdio fix:** the MCP client forces the child process to UTF-8 so the
  stdio JSON-RPC channel doesn't choke on non-ASCII bytes.

## Agent mode

`POST /extract/agent` runs a genuine tool-calling agent: the model is given the
note and a tool set (`extract_medical_info`, `validate_extraction`,
`repair_extraction`, `generate_assessment`, `lookup_icd10`, `verify_grounding`,
`finish`) and decides the order itself. Each tool runs server-side against the
existing pipeline, so the planner sequences the work while the tools do the real
extraction — the values never come from the planner's imagination. Conditional
execution is real: ICD-10 is called only when a diagnosis exists. If the planner
stalls or errors, it falls back to the deterministic pipeline, so the endpoint
always returns a valid result. The `qc_confidence` is a quality-control score
(schema valid? items grounded? no unsupported diagnosis?), never a medical one.

## Stack

Python 3.11 | FastAPI | Pydantic v2 | Groq (OpenAI-compatible) | Ollama fallback |
MCP (FastMCP, stdio) | rapidfuzz | httpx | pytest. Frontend: React + Vite + TypeScript + Tailwind.
