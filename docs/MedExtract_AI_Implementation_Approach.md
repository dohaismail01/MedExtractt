# MedExtract AI — Implementation Approach

A practical roadmap for building and explaining MedExtract AI. Reorganized from
`MedExtract_AI_Project_Proposal.md` — same idea, data, technologies, and
decisions; nothing new invented. Results that don't exist yet are marked **TBD**;
anything not yet built is marked **Planned**.

---

## 1. Project Overview

- **What it does:** turns an unstructured clinical note into a fixed, validated
  JSON object with ten medical fields.
- **Problem it solves:** clinical notes are free text, so their content
  (symptoms, diagnoses, medications, follow-up) can't be used by any downstream
  system without manual re-entry.
- **Expected input:** one clinical note (pasted text or an uploaded `.txt`).
- **Expected output:** one JSON object with the same ten fields every time.
- **Main goal:** demonstrate **prompt engineering** that extracts only what the
  note states — an empty field is a correct answer. The system never diagnoses,
  never recommends treatment, and never invents missing information.

One line: *paste a note, get back clean structured JSON that contains only what
the note actually says.*

---

## 2. Dataset

- **Name:** Patient Diaries and Clinical Notes Dataset (Kaggle).
- **Source:** Kaggle, as provided by the mentor. No real patient-identifiable
  information.
- **What it contains:** short clinical/diary text plus a **classification
  `label`** (`depression` / `no depression`). **It does not contain
  ground-truth labels for the ten extraction fields** — only the class label.
- **How the notes are used:** the note text is the input to the extraction
  pipeline. The Kaggle `label` is a *classification target*, kept separate and
  shown on its own, never mixed into the ten extraction fields.
- **How data is used during development:** notes are split into three sets that
  never mix, so we never evaluate on text used to build the prompt.

| Set | What it is | Purpose |
|---|---|---|
| **Original dataset** | Raw Kaggle rows (note + class label) | Source of all notes |
| **Scratch set** | ~10 real rows, no extraction labels | Prompt iteration only |
| **Gold set** | ~15 real rows, **hand-labeled** for the 10 fields | Precision/recall/F1 scoring |
| **Adversarial set** | ~6 real rows chosen for guardrail stress | Prove no-invention behavior |

The gold and adversarial labels are **annotations we add by hand** to real
notes — not data invented by the model, and not something the dataset shipped
with.

---

## 3. System Objective

Extract exactly these ten fields, in this order, on every response:

| # | Field | Type | Empty value |
|---|---|---|---|
| 1 | `chief_complaint` | string \| null | `null` |
| 2 | `symptoms` | list[str] | `[]` |
| 3 | `diagnosis` | list[str] | `[]` |
| 4 | `medical_history` | list[str] | `[]` |
| 5 | `medications` | list[object] | `[]` |
| 6 | `procedures` | list[str] | `[]` |
| 7 | `follow_up` | string \| null | `null` |
| 8 | `summary` | string \| null | `null` |
| 9 | `risk_indicators` | list[str] | `[]` |
| 10 | `urgency` | `low` / `medium` / `high` \| null | `null` |

**Medication sub-fields** (one object per drug):

| Sub-field | Example |
|---|---|
| `name` | `"metformin"` |
| `dose` | `"500mg"` |
| `frequency` | `"BID"` |
| `duration` | `"3 months"` |

**Missing-value behavior:**
- Missing single value → `null`
- Missing list → `[]`
- A medication with only a name still returns all four sub-fields (three `null`).
- The shape is identical for every note, regardless of content.

---

## 4. Overall Approach

High-level pipeline:

```
Clinical Note
  → Prompt
  → LLM
  → Structured JSON
  → Validation (Pydantic)
  → Repair if needed
  → Summary / Risk / Urgency
  → Optional ICD-10 (MCP)
  → Final Response
```

Each stage in plain language:
1. **Prompt** — a versioned system prompt tells the model the rules and the exact
   output shape.
2. **LLM** — the model reads the note and returns JSON.
3. **Structured JSON** — the seven extraction fields.
4. **Validation** — Pydantic checks the JSON matches the schema exactly.
5. **Repair if needed** — if invalid, the specific error is sent back to the
   model to fix (capped).
6. **Summary / Risk / Urgency** — a second call produces the three assessment
   fields *from the validated JSON only*.
7. **Optional ICD-10 (MCP)** — if a diagnosis exists, look up its code via a real
   tool, never from the model's memory.

---

## 5. Architecture

```
  ┌─────────────────────────────────────┐
  │  REACT FRONTEND  (:5173)            │
  │  • note input / file upload         │
  │  • extraction cards + assessment    │
  │  • evaluation / prompt comparison   │
  │  NO api key · NO prompts · NO model │
  └──────────────┬──────────────────────┘
                 │  HTTP · JSON · CORS
                 v
  ┌─────────────────────────────────────┐
  │  FASTAPI BACKEND  (:8000)           │
  │  • API + prompt files + LLM calls   │
  │  • pipeline orchestration           │
  │  • Pydantic validation + repair     │
  │  • MCP client                       │
  └────────┬──────────────────┬─────────┘
           │                  │  stdio (MCP)
           v                  v
      Groq API         ┌──────────────────┐
                       │  icd10_mcp       │
                       └────────┬─────────┘
                                v
                       NLM API / CMS CSV
```

**Frontend — React + Vite + TypeScript + Tailwind.** Responsibilities: note
input, file upload, displaying results as cards, and the evaluation / prompt
comparison view. Holds no key, no prompts, no model logic.

**Backend — Python + FastAPI + Uvicorn.** Responsibilities: the API, prompt
management, LLM calls, pipeline orchestration, Pydantic validation, the repair
loop, and acting as the MCP client. The API key and prompt files live here only.

**LLM — Groq (OpenAI-compatible API).** Primary model `openai/gpt-oss-120b`;
`openai/gpt-oss-20b` for faster prompt iteration; `qwen2.5:7b` via Ollama as an
offline fallback. Chosen for a free tier, native function calling, and high
throughput (prompt iteration means re-running the same notes repeatedly).

**Validation — Pydantic v2.** The response model *is* the schema. Its per-field
error messages are what feed the repair loop, so error quality drives repair
success.

**MCP — FastMCP over stdio.** A standalone `icd10_mcp` server exposes an ICD-10
lookup tool; FastAPI consumes it as an MCP client. Responsible only for turning a
diagnosis string into an ICD-10 code from an authoritative source (NLM API, with
a local CMS CSV fallback).

---

## 6. Detailed Processing Pipeline

### Step 1 — Receive clinical note
```
POST /extract
{ "note": "..." }
```
Optional query params: `?version=v1|v2|v3|final`, `?format=fhir`.

### Step 2 — Call 1: Extraction
- Uses the selected versioned prompt + the note wrapped in `<note>…</note>`.
- The model receives the rules and the note; it returns JSON for the **seven**
  extraction fields (`chief_complaint`, `symptoms`, `diagnosis`,
  `medical_history`, `medications`, `procedures`, `follow_up`).

### Step 3 — Validate the output
- Validated against the Pydantic `Extraction` schema (`extra="forbid"`, so an
  invented 11th key fails instead of passing silently).
- **Valid:** continue to Step 5.
- **Invalid:** go to Step 4.

### Step 4 — Repair loop
```
LLM → Invalid JSON → Pydantic error
    → Repair prompt (the exact error) → LLM → Validate again
```
- The **specific** validation error is fed back, not a generic retry.
- Capped at 2 retries so an unfixable case can't loop forever.
- If repair is exhausted, the valid **empty** schema is returned and the failure
  is surfaced (in a response header / the evaluation), never hidden.

### Step 5 — Call 2: Summary / Risk / Urgency
- Receives the **validated extracted JSON, not the original note.**
- Returns `summary`, `risk_indicators`, `urgency`.
- **Why this matters:** because the note is not in Call 2's context at all, that
  step is structurally unable to introduce a fact the note didn't contain. The
  no-hallucination rule becomes a property of the design, not a request to the
  model.

### Step 6 — Optional Agentic AI / MCP
An **orchestration layer** decides which tools/actions the workflow needs — it is
not a chatbot and it does not perform medical diagnosis or clinical
decision-making. It only sequences the extraction/validation/lookup steps.

```
Clinical Note
  → Agent
  → Extraction tool
  → Validation tool
  → Repair tool (if invalid)
  → Assessment
  → ICD-10 lookup (only if a diagnosis exists)
  → Verification
  → Final result
```

- **What the agent decides:** the order of tool calls, and whether a diagnosis
  exists (so whether ICD-10 is needed).
- **Tools it can call:** `extract_medical_info`, `validate_extraction`,
  `repair_extraction`, `generate_assessment`, `lookup_icd10`, `verify_grounding`,
  `finish`.
- **ICD-10 called** only when the extraction has a non-empty diagnosis list;
  **skipped** when diagnosis is empty.
- **How tool results are used:** each tool runs server-side against the existing
  pipeline, so the agent orchestrates while the tools produce the real values —
  the model cannot invent field contents. Codes come only from the tool result.
- **Why it's agentic:** conditional tool use and decision-making based on what it
  finds, with a visible step-by-step trace — not a single fixed prompt.

---

## 7. Prompt Engineering Approach

Four versions, each fixing failures logged from the previous one. The
progression is the graded core.

```
V1 → V2 → V3 → Final
```

| Version | What it adds | Problem addressed | Why | How evaluated |
|---|---|---|---|---|
| **V1** | Role + bare key list, no rules | — (baseline) | Establish the failure floor | Metrics as the reference point |
| **V2** | No-hallucination, explicit-only, missing-value, negation | V1 invents diagnoses; keeps negated findings | Make grounding + negation explicit | Hallucination rate, negation checks |
| **V3** | Worked example, medication rules, ambiguity, delimiters-as-data | V2 mishandles medication sub-fields; ambiguous cases | Structured medication extraction; injection safety | Medication accuracy, guardrail set |
| **Final** | Output-format enforcement, urgency constraint, cross-record consistency | V3 formatting/consistency drift | Lock the exact shape | Validity, precision, consistency |

Each version is recorded as **failure observed → change made → measured result**
in `prompts/CHANGELOG.md`. A version that moves no metric does not ship. Measured
results: **TBD** (populated after the evaluation sweep runs against a live key).

---

## 8. Guardrails

Rules the system must hold:
- Extract only information **explicitly stated** in the note.
- Do **not** infer diagnoses; a symptom cluster is never promoted to a diagnosis.
- Do **not** invent medications or doses.
- Handle **negation** correctly ("denies chest pain" → not a symptom).
- Do **not** convert symptoms into diagnoses.
- Do **not** recommend treatment.
- Missing information stays `null` / `[]`.
- `risk_indicators` and `urgency` are limited to what the extracted entities
  support (they default to empty rather than reaching).

**How they're tested:** an adversarial set of real notes, each with an assertion
(e.g. a mood note must yield `diagnosis == []`; a medication named without a dose
must keep `dose == null`). Target: 100% pass — **result TBD** until run live.

---

## 9. Evaluation Approach

Metric definitions are frozen before any result exists, and each number is
produced only by the frozen scoring functions.

| Metric | Meaning |
|---|---|
| **JSON validity** | Share of responses that parse + pass schema — reported **before and after** the repair loop |
| **Precision** | Of the items extracted, how many are correct |
| **Recall** | Of the correct items, how many were extracted |
| **F1** | Harmonic mean of precision and recall |
| **Medication name accuracy** | Did it find the right drugs (name is the identity key) |
| **Medication sub-field accuracy** | dose / frequency / duration correct on found drugs |
| **Hallucination rate** | Share of extracted items not grounded in the note (negation-aware) |
| **Guardrail pass rate** | Share of adversarial notes whose assertions hold |

- **V1 → Final comparison:** the same gold + adversarial sets are scored for all
  four prompt versions, producing one comparison table. Expected direction:
  precision/recall/F1/validity rise, hallucination falls — **actual numbers
  TBD**.
- **Why the gold set is hand-labeled:** using an LLM to judge extraction would
  mean an LLM grading an LLM on exactly the failure mode being tested.
- **Why the sets stay separate:** scoring against notes used to develop the
  prompt would measure memorization, not quality.

> No results are fabricated. The harness is built; the table is generated by
> running it against a live model (`python -m eval.run_eval`).

---

## 10. UI / Final Output

Focused on structured extraction, not a chat interface.

**Input**
- Clinical note textarea / `.txt` upload → "Extract Information".

**Extraction Results** (cards)
- Chief complaint · Symptoms · Diagnosis · Medical history · Medications
  (name/dose/frequency/duration) · Procedures · Follow-up.
- Empty fields render explicitly ("None stated" / "Not explicitly stated").

**Assessment**
- Summary · Risk indicators · Urgency (colour-coded).

**Technical information**
- Validation status (schema validated / after repair).
- View / Copy JSON.
- Optional ICD-10 result (diagnosis → code → tool verification).
- Optional provenance / evidence (which note span supports each item).
- Optional Agent Activity panel (the tool trace + a quality-control confidence).

The Kaggle **dataset label** is shown in its own card, clearly separate from the
extraction.

---

## 11. Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind | Input, result cards, comparison view |
| Backend | Python + FastAPI + Uvicorn | API, orchestration, LLM calls |
| Validation | Pydantic v2 | Schema = response model; feeds repair loop |
| LLM provider | Groq (OpenAI-compatible) | Model calls, native tool calling |
| Primary model | `openai/gpt-oss-120b` | Final pipeline |
| Iteration model | `openai/gpt-oss-20b` | Faster prompt iteration |
| Offline fallback | Ollama + `qwen2.5:7b` | Demo-day insurance |
| Agent tooling | MCP (FastMCP, stdio) | ICD-10 lookup as a reusable tool |
| ICD-10 source | NLM Clinical Table Search API + CMS CSV | Authoritative codes, offline fallback |
| Testing | pytest | Guardrail rules as regression tests |
| Data | pandas, `.jsonl` | Kaggle CSV + test sets / results |

---

## 12. Implementation Phases

| Phase | Goal | What I will do | Output | Done when |
|---|---|---|---|---|
| **0 — Foundation** | Confirm ground truth | Verify live model IDs; one note in, raw text out; diff field names vs spec | A working model call | One note → raw output against a live model |
| **1 — Baseline** | Failure floor | Write the Pydantic schema; run prompt V1 on scratch notes; log every failure | Categorized failure log | V1 run and failures documented |
| **2 — Prompt iteration** | Turn failures into gains | Write V2/V3/Final tied to logged failures; build the repair loop | Final prompt + repair loop + changelog | Each version traceable to a fixed failure |
| **3 — Evaluation** | Primary deliverable | Hand-label gold + adversarial; implement + unit-test metrics; score all versions | V1→Final comparison table | All four versions scored under identical settings |
| **4 — Application layer** | Make it a service | Wire Call 2; build API + CORS; build the React UI | Working web app | A note submitted in the UI renders a valid result |
| **5 — Agent integration (bonus)** | Ground diagnoses | Build `icd10_mcp`; consume it as an MCP client; force the CSV fallback once | Standalone server + integrated lookup | Every code traceable to a logged tool result |
| **6 — Guardrail validation** | Prove scope limits | Run the full adversarial set; finalize changelog, write-up, README | Submission-ready project | 100% adversarial pass |

Critical path: **0 → 1 → 2 → 3 → 6**. Phase 4 can start after Phase 2. Phase 5 is
optional.

---

## 13. What I Will Show My Mentor

1. Give the system a clinical note.
2. Show the extraction (the ten fields as cards).
3. Show validation (schema validated / repaired).
4. Show repair when the first output is invalid.
5. Show summary / risk / urgency (Call 2, from validated JSON only).
6. Show the agent / tool decision-making (the Agent Activity trace).
7. Show the ICD-10 lookup when a diagnosis exists (and that it's skipped when not).
8. Show the V1 vs Final evaluation table.
9. Show the guardrail results on adversarial notes.
10. Show the final architecture (frontend / backend / MCP).

*(Live extraction, the eval table, and guardrail numbers require a working Groq
key; until then those are demonstrated as TBD.)*

---

## 14. Core vs Bonus

**Must have (the graded core)**
- Core extraction (the ten fields)
- Prompt engineering (V1 → Final)
- Validation (Pydantic)
- Repair loop
- Evaluation (V1 → Final table)
- Guardrails (adversarial set)

**Should have**
- The web application (demonstrable, but the pipeline is provable without a UI)

**Bonus**
- Agentic / MCP ICD-10 integration
- Provenance spans
- FHIR export
- Drug interaction flags

Descope order if time runs short (first to cut first): ICD-10/MCP → FHIR export →
React comparison/eval screens → collapse the two calls into one → shrink the gold
set. Never descoped: the adversarial run and the V1→Final table.

---

## 15. Final One-Paragraph Explanation

> I am building **MedExtract AI**, a system that reads a free-text **clinical
> note** and returns a fixed, validated JSON object with ten fields —
> **structured extraction** of what the note actually says. It uses an **LLM**
> (Groq) driven by carefully **engineered prompts** that I improve across four
> documented versions. Every output is checked with **Pydantic validation**, and
> when the model returns something invalid a capped **repair loop** feeds the
> exact error back to fix it. A second call produces the summary, risk
> indicators, and urgency from the validated data only — never the raw note — so
> it can't invent facts. I measure the whole thing with a hand-labeled gold set
> and an **evaluation** that compares the naive prompt to the final one. As a
> bonus, an **agentic/tool orchestration** layer lets the model decide which
> tools to run and calls an **ICD-10 lookup over MCP** only when a diagnosis is
> present. The guiding rule throughout is that an empty field is a correct
> answer — the system extracts, it does not diagnose or invent.
