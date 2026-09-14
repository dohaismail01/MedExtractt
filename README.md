# MedExtract

**An LLM-powered system that turns unstructured clinical notes into a consistent, validated JSON structure — with ICD-10 code suggestions as a bonus.**

MedExtract reads a free-text clinical note and extracts only what is *explicitly*
stated — chief complaint, symptoms, diagnoses, medical history, medications,
procedures, and follow-up — then adds a grounded summary and documentation-based
risk/urgency flags. Every extracted fact is grounded to a verbatim span in the
note (facts that can't be located are dropped), which is how the system stays
closed-world and avoids inventing information. The project's focus is **prompt
engineering, structured output, validation, and evaluation**, not a raw API call.

> ⚠️ Research/educational prototype. ICD-10 codes are suggestions for clinician
> review, not final coding. Risk/urgency reflect language in the note, not a
> triage judgement. Not fit for clinical use without further validation.

---

## ✨ Key Features

- **Structured extraction** of symptoms, diagnoses, medications, medical history,
  procedures, and follow-up from free text.
- **Medication parsing** into `name` / `dose` / `frequency` / `duration`.
- **Evidence grounding** — each fact is matched to a verbatim substring of the
  note; unsupported facts are dropped and counted (anti-hallucination).
- **Schema validation + bounded repair** — invalid model output is re-prompted a
  limited number of times, then fails cleanly (never returns a guessed object).
- **Grounded summary** built only from validated data (the raw note is not
  passed to the summarizer).
- **Documentation-based risk/urgency** from an auditable term lexicon (`low` /
  `medium` / `high`).
- **Prompt versioning** (V1 → V2 → V3 → Final) so prompt improvements are
  demonstrable and swappable via config.
- **ICD-10 code suggestions (bonus)** via a bounded, tool-using agent over a
  local ICD-10-CM dataset.
- **FastAPI backend** returning the brief's exact flat JSON schema, plus a small
  **React + TypeScript demo UI**.

---

## 🧠 How It Works

```text
Clinical note
     ↓
Validate / (optional) PHI redaction
     ↓
Extraction  ──►  LLM  (driven by a versioned prompt)
     ↓
Structural validation (Pydantic)  ──► invalid? ──► bounded repair (re-prompt)
     ↓
Evidence grounding (drop facts not found in the note)
     ↓
┌──────────────┬───────────────┬──────────────────┐
│ Grounded     │ Risk / urgency │ ICD-10 agent      │
│ summary      │ (lexicon)      │ (bonus)           │
└──────────────┴───────────────┴──────────────────┘
     ↓
Flat JSON response (brief schema)
```

The LLM produces a richer internal shape (each fact carries `status` and an
`evidence` span). The validator grounds that evidence against the note; the API
then **flattens** the result to the project's required flat schema
(`src/medextract/brief.py`). Evidence offsets and status stay internal.

---

## 🏗️ System Architecture

```text
          ┌──────────────────┐
          │  React UI (Vite) │
          └────────┬─────────┘
                   │  POST /extract
          ┌────────▼─────────┐
          │  FastAPI backend │
          └────────┬─────────┘
                   │
          ┌────────▼─────────┐      ┌──────────────────┐
          │  Orchestrator    │─────►│ LLM client       │
          │  (pipeline)      │      │ (adapter)        │
          └────────┬─────────┘      └──────────────────┘
                   │
   ┌───────────────┼─────────────────┐
   ▼               ▼                 ▼
extract/validate  risk/summary   ICD-10 agent → local ICD-10-CM (SQLite FTS)
```

The **LLM client is an adapter** — swapping models (Groq, Ollama, any
OpenAI-compatible endpoint) never touches pipeline code.

---

## 📁 Project Structure

```text
MEDExtract/
├── src/medextract/
│   ├── schemas.py          # Pydantic v2 models (single source of truth)
│   ├── brief.py            # flatten internal model → brief's flat JSON schema
│   ├── config.py           # env-driven settings (pydantic-settings)
│   ├── orchestrator.py     # wires the full pipeline
│   ├── safety.py           # PHI redaction, note validation, disclaimer
│   ├── prompts/            # extraction_v1..final.md, repair.md, summary.md + CHANGELOG
│   ├── llm/                # LLMClient protocol + stub / ollama / openai_compat
│   ├── pipeline/           # extract, validate, repair, summary, risk
│   ├── icd10/              # source (SQLite FTS) + tools + bounded agent (bonus)
│   └── api/                # FastAPI app factory + routes
├── eval/                   # run_eval.py, metrics.py, datasets/, reports/
├── tests/                  # test-suite mirroring the package
├── frontend/               # React + TypeScript + Vite demo UI
├── reference/              # icd10_common.csv (local ICD-10-CM fallback data)
├── docs/                   # SPEC.md (build contract) + approach.md (design rationale)
├── pyproject.toml
└── .env.example
```

---

## 🤖 AI / ML Approach

MedExtract is an **LLM information-extraction** system. It does **not** train a
model, use embeddings/vector search, or do RAG.

**Extraction model (LLM).** An instruction-tuned chat model performs the
extraction, driven by a versioned prompt at temperature 0 with JSON output. The
model is configurable; the project was built to run against **Groq (GPT-OSS)** or
a local **Ollama** model. A deterministic offline `stub` extractor also exists —
but only so tests run without a network or key; it ignores prompt text and is not
the product path.

**Prompt engineering (the core focus).** Four prompt versions live in
`src/medextract/prompts/`, each motivated by observed failures (see
[CHANGELOG](src/medextract/prompts/CHANGELOG.md)):

| Version | Change |
|---|---|
| **V1** | Baseline: extract-only, evidence required, status enum, output shape |
| **V2** | Physician-facing role; each assertion status defined with trigger cues |
| **V3** | Explicit negation/uncertainty, medication, ambiguity & consistency rules + a worked example |
| **Final** | Reorganized around the nine brief-mandated elements, each a labelled, auditable section |

Select one with `MEDEXTRACT_PROMPT_VERSION=v1|v2|v3|final`.

**Evidence grounding (anti-hallucination).** After the LLM responds, every fact's
`evidence` string is located in the note (exact match, then a `rapidfuzz`
near-match fallback). Facts that can't be grounded are dropped and counted as
`unsupported`, giving an honest hallucination signal.

**ICD-10 agent (bonus).** A bounded, tool-using loop resolves each *validated*
diagnosis to an ICD-10-CM code using named tools (`search_codes`, `lookup_code`,
`validate_code`, `get_category`). By default it queries the live **NLM Clinical
Table Search Service** (public US ICD-10-CM API, no key), falling back to a
bundled local SQLite FTS dataset when offline (`ICD10_BACKEND=nlm|local_sqlite`).
It is capped
(5 calls/term, 25/note), records a `resolution_path`, and **abstains**
(`code: null`, `needs_review: true`) below a confidence threshold rather than
guessing. Procedures are left uncoded (no ICD-10-PCS source wired).

---

## 📊 Dataset

- **Original source dataset:** the public Kaggle *Patient Diaries and Clinical
  Notes Dataset*. Check its license before redistributing.
- **Evaluation dataset:** the real HuggingFace
  [`chenhaodev/medical-dialogs-notes`](https://huggingface.co/datasets/chenhaodev/medical-dialogs-notes)
  (225 real clinical notes; columns `id`, `dialogue`, `clinical_note`). The eval
  runs on the `clinical_note` field. **No synthetic/generated data is used.**
- Build the eval set locally (not committed — regenerated from HuggingFace, and
  subject to that dataset's license):

  ```bash
  python -m eval.prepare_hf_dataset          # -> eval/datasets/medical_dialogs_notes.jsonl
  ```
- These notes carry **no gold-standard labels**, so the harness reports the
  label-free quality metrics (schema validity, unsupported-extraction rate,
  repair rate, ICD-10 abstention, latency). Precision/recall/F1 require a labelled
  set and are shown only when a dataset provides `gold` labels.
- No real patient-identifiable data is used.

---

## ⚙️ Installation

Requires **Python 3.11+**.

```bash
git clone <repository-url>
cd MEDExtract

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -e .            # installs medextract (from src/) + dependencies
```

For the demo UI you also need **Node.js 18+**.

---

## 🔐 Environment Variables

All variables have defaults (the app runs offline on the `stub` provider with no
config). Copy `.env.example` to `.env` to override.

| Variable | Purpose | Required |
|---|---|---|
| `MEDEXTRACT_LLM_PROVIDER` | `stub` \| `ollama` \| `openai_compat` | No (default `stub`) |
| `MEDEXTRACT_MODEL` | Model name/id | For real LLM |
| `MEDEXTRACT_LLM_BASE_URL` | OpenAI-compatible base URL (e.g. Groq) | For `openai_compat` |
| `MEDEXTRACT_LLM_API_KEY` | API key for the provider | For `openai_compat` |
| `MEDEXTRACT_PROMPT_VERSION` | `v1` \| `v2` \| `v3` \| `final` | No (default `v1`) |
| `MAX_REPAIR_ATTEMPTS` | Repair retries on invalid output | No (default `2`) |
| `MEDEXTRACT_API_KEY` | Optional API-key auth for the backend | No |
| `MEDEXTRACT_REDACT_INPUT` | Redact PHI before processing | No (default `false`) |

See [.env.example](.env.example) for the full list (ICD-10 bounds, CORS, body cap,
log level). **Never commit real keys.**

Example — Groq (GPT-OSS):

```bash
MEDEXTRACT_LLM_PROVIDER=openai_compat
MEDEXTRACT_MODEL=openai/gpt-oss-20b        # or openai/gpt-oss-120b
MEDEXTRACT_LLM_BASE_URL=https://api.groq.com/openai/v1
MEDEXTRACT_LLM_API_KEY=gsk_...
```

---

## 🚀 Usage

### Backend

```bash
uvicorn medextract.api.app:app --reload    # http://127.0.0.1:8000/docs
```

Extract from a note:

```bash
curl -s http://127.0.0.1:8000/extract \
  -H 'Content-Type: application/json' \
  -d '{"note": "Severe chest pain radiating to the arm. Denies SOB. Hx hypertension. Dx acute MI. Amlodipine 5 mg daily."}'
```

Returns the flat schema: `chief_complaint`, `symptoms[]`, `diagnosis[]`,
`medical_history[]`, `medications[]`, `procedures[]`, `follow_up`, `summary`,
`risk_indicators[]`, `urgency`, `icd10_codes[]`.

Other endpoints: `GET /health` (status, model, prompt version, disclaimer),
`POST /redact` (PHI redaction preview).

### Frontend

```bash
cd frontend
npm install
npm run dev                                 # http://localhost:5173
```

The UI defaults to the backend at `http://127.0.0.1:8000` (override with
`VITE_API_URL`).

### Evaluation

```bash
python -m eval.run_eval                     # writes a report to eval/reports/
python -m eval.run_eval --prompt-version final   # compare a prompt version
```

---

## 🖥️ Demo

Screenshots / demo video coming soon. The UI lets you paste a note, run
extraction, and see the structured fields, medications table, risk/urgency,
ICD-10 suggestions, and the matched terms highlighted in the note.

---

## 📈 Results & Evaluation

Evaluation runs on the real HuggingFace notes (see **Dataset**), so the harness
reports the **label-free** quality metrics — unsupported-extraction rate, schema
first-pass validity, repair rate, ICD-10 abstention rate, mean tool calls, and
p50/p95 latency. Precision/recall/F1 require gold labels and are reported only if
a labelled dataset is supplied.

Reproduce (needs a real LLM — e.g. Groq GPT-OSS — set in `.env`):

```bash
python -m eval.prepare_hf_dataset            # build the eval set from HuggingFace
python -m eval.run_eval                       # single run -> eval/reports/
python -m eval.compare_prompts                # V1→V2→V3→Final comparison
```

`compare_prompts` saves each prompt version's per-note outputs to
`eval/reports/prompt_runs/<version>.jsonl` and writes a comparison report
(`eval/reports/prompt_comparison.md`) with the metric deltas and the rationale for
each prompt revision — the artifact that demonstrates the prompt-engineering
progression.

> No numbers are quoted here: the offline `stub` ignores prompt text, so a
> genuine LLM run is required before reporting performance. Metrics are written to
> `eval/reports/` when you run the commands above.

---

## 🧪 Testing

```bash
python -m pytest
```

**54 tests** cover schemas, validation + evidence grounding, repair, risk &
summary (including a no-new-facts assertion), the ICD-10 agent, safety/redaction,
and the orchestrator + API. Tests are forced onto the `stub` provider so they run
offline and deterministically.

---

## 🛡️ Safety & Limitations

- **Intended use:** extracting and summarizing information already present in a
  note; educational/research use.
- **Not intended for:** diagnosis, treatment recommendation, or triage. The
  system never adds a clinical fact not in the note.
- **Privacy:** best-effort PHI/PII redaction utility and a `/redact` endpoint;
  raw note text is not logged at INFO+. This is **not** certified
  de-identification (regex redaction misses free-text names).
- **Hallucination:** evidence grounding reduces but does not eliminate it; the
  unsupported-extraction rate is the honest measure of what remains.
- **ICD-10 suggestions** require clinician review and are not billing-ready.
- Known weak spots: negation, uncertainty, and abbreviations (targeted by the
  prompt iterations and tests).

---

## 🔮 Future Improvements

- Run and report evaluation with a real LLM (Groq GPT-OSS / Ollama).
- Expand the eval set to the full Kaggle *Patient Diaries and Clinical Notes*
  dataset (larger, non-overlapping, held-out).
- Head-to-head prompt comparison (V1→Final) on the identical subset.
- ICD-10-PCS procedure coding and an optional MCP-backed ICD-10 source.
- `mypy --strict` gate and expanded adversarial test cases.

---

## 👩‍💻 Contributors

- Doha Ismail ([@dohaismail01](https://github.com/dohaismail01))

---

## 📄 License

No license file is currently included. Add one (e.g. MIT) before public
distribution.
