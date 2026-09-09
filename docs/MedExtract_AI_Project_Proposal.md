# MedExtract AI — Project Proposal

**Clinical Notes → Structured Medical Information**


---

## 1. Executive Summary

Clinical notes are written as free text. The information inside them — symptoms, diagnoses, medications, follow-up plans — is unstructured and therefore unusable by any downstream system without manual re-entry.

**MedExtract AI** is a two-tier web application that converts an unstructured clinical note into a fixed, validated JSON object. A **React** frontend handles input and presentation; a **FastAPI** backend runs the prompt pipeline, validates the output against a strict schema, and returns structured data.

The project's centre of gravity is prompt engineering, not model selection. Four documented prompt versions are developed, each fixing failures observed in the previous one, and measured against a hand-labeled test set. The evaluation table comparing V1 to Final is the primary deliverable.

**The defining constraint** is that the system extracts only what the note already states. It does not diagnose, does not recommend treatment, and does not fill gaps with plausible content. An empty field is a correct answer — and the system is graded on producing one when the note gives it nothing.

---

## 2. Objectives

| # | Objective | Evidence of success |
|---|---|---|
| 1 | Extract structured medical information from unstructured notes | Per-field precision and recall against a hand-labeled gold set |
| 2 | Demonstrate measurable prompt improvement | A V1→Final comparison table with metrics defined in advance |
| 3 | Guarantee schema-valid output | Validity rate reported before and after the repair loop |
| 4 | Prevent hallucination and scope violation | 100% pass on an adversarial guardrail set |
| 5 | Ground diagnoses in a real coding standard *(bonus)* | Every ICD-10 code traceable to a logged tool result |

---

## 3. Scope

### In scope

- Extraction of the ten specified fields from a single clinical note
- Prompt design, versioning, and documented iteration
- Schema validation with a retry-and-repair loop
- Evaluation harness and metrics
- Web interface for demonstration
- ICD-10 code lookup via an MCP server (bonus)

### Explicitly out of scope

The system **does not**:

- Provide medical diagnosis or clinical judgment
- Recommend, prescribe, or adjust treatment
- Infer information the note does not state
- Process real patient-identifiable data — the Kaggle dataset used contains no real patient-identifiable information

It **may** flag risk indicators and urgency, strictly limited to what the extracted entities already support.

> **Why this matters.** These aren't disclaimers appended to a finished system; they're the requirement the architecture is built around. Section 5 explains how the two-call design makes the no-invention rule structural rather than instructional.

---

## 4. Proposed Architecture

```
  ┌─────────────────────────────────────┐
  │  REACT FRONTEND                     │
  │  • note input / file upload         │
  │  • renders the 10 fields as cards   │
  │  • prompt-version comparison view   │
  │  NO api key · NO prompts · NO model │
  └──────────────┬──────────────────────┘
                 │  HTTP · JSON · CORS
                 v
  ┌─────────────────────────────────────┐
  │  FASTAPI BACKEND                    │
  │  • holds the API key and prompts    │
  │  • two-call extraction pipeline     │
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

### Why the tiers are split

**The API key can never reach the browser.** Anything shipped to React is readable by anyone who opens developer tools. That single constraint determines what lives where — every credential, every prompt file, and every model call stays server-side.

The prompt files stay on the backend for the same reason: they are this project's graded artifact.

### Responsibilities

| Component | Owns | Holds no |
|---|---|---|
| **React frontend** | User input, presentation, result rendering | Credentials, prompts, model logic |
| **FastAPI backend** | Pipeline orchestration, validation, model calls | — |
| **MCP server** | ICD-10 lookup against an authoritative source | Application state |

---

## 5. Proposed Pipeline

The assignment specifies this flow:

> Clinical Note → Prompt → LLM → JSON Output → Validation → Summary / Risk Flags → Final Response

Summary and risk flagging come **after** validation. This proposal implements that literally, as two separate model calls.

```
  POST /extract  { "note": "..." }
        |
        v
  CALL 1   Prompt + <note>...</note>
           -> 7 extraction fields
        |
        v
  VALIDATE  Pydantic  --- invalid ---> repair loop (capped retries)
        |                              feeds the error back to the model
        v
  CALL 2   validated JSON only, NOT the note
           -> summary, risk_indicators, urgency
        |
        v
  VALIDATE
        |
        v
  CALL 3   ICD-10 lookup via MCP tool call        [bonus]
           -> icd10_codes
        |
        v
  200   final JSON response
```

**Call 1 — Extraction.** The prompt plus the note, wrapped in `<note>` delimiters. Returns `chief_complaint`, `symptoms`, `diagnosis`, `medical_history`, `medications`, `procedures`, `follow_up`. On validation failure, the specific error is fed back to the model rather than a generic retry.

**Call 2 — Summary and risk flags.** The **validated output of Call 1** goes in. **The raw note does not.** Returns `summary`, `risk_indicators`, `urgency`.

*This is the central design decision.* Because the note is not in Call 2's context at all, that step is structurally incapable of introducing a fact the note didn't contain. The no-hallucination rule stops being something the model is asked to respect and becomes something it cannot violate. The cost is one extra call per note, which is negligible at this scale.

**Call 3 — ICD-10 lookup (bonus).** The validated diagnosis list is sent with a tool schema discovered from the MCP server. The model requests the lookup; the backend intercepts it, executes it against a real coding API, and returns the result. Codes are assembled in code from logged tool results — never from the model's own knowledge.

---

## 6. Output Specification

Every response, regardless of input, returns exactly this structure:

```json
{
  "chief_complaint": null,
  "symptoms": [],
  "diagnosis": [],
  "medical_history": [],
  "medications": [
    { "name": null, "dose": null, "frequency": null, "duration": null }
  ],
  "procedures": [],
  "follow_up": null,
  "summary": null,
  "risk_indicators": [],
  "urgency": null
}
```

| Field | Type | Empty | Rule |
|---|---|---|---|
| `chief_complaint` | str \| null | `null` | As stated. Not inferred from symptoms. |
| `symptoms` | list[str] | `[]` | Negated findings excluded. |
| `diagnosis` | list[str] | `[]` | Only if named. A symptom cluster is never promoted. |
| `medical_history` | list[str] | `[]` | Conditions framed as past. |
| `medications` | list[object] | `[]` | Four sub-fields each; unstated ones are `null`. |
| `procedures` | list[str] | `[]` | Performed or ordered, never speculative. |
| `follow_up` | str \| null | `null` | Stated intent only. |
| `summary` | str \| null | `null` | From extracted content only. |
| `risk_indicators` | list[str] | `[]` | Flagging, not diagnosis. |
| `urgency` | str \| null | `null` | Constrained to `low` / `medium` / `high`. |

**Contract rules.** Missing single value → `null`. Missing list → `[]`. Schema identical across every record. A medication with only a name still returns all four sub-fields, three of them `null`. An empty medication list is `[]`, not a list containing one all-null object.

> **The bonus adds an 11th key.** `icd10_codes` maps each extracted diagnosis to its code or `null`. Strict validation runs against the 10-field model, so spec compliance stays verifiable independently of the extension.

---

## 7. Prompt Engineering Approach

The assignment forbids jumping straight to a final prompt, and prompt design is the graded core. Four versions, each addressing failures observed in the previous one, with prompts and results retained as evidence.

| Version | Adds | Driven by |
|---|---|---|
| **V1** | Role plus the bare key list. No rules, no examples. | Baseline — establishes the failure floor. |
| **V2** | Grounding, no-promotion, negation, history, missing-value behaviour. | V1's logged failures. |
| **V3** | Worked example, medication extraction rules, ambiguity handling, delimiters-as-data. | V2's logged failures. |
| **Final** | Output-format enforcement, urgency enum discipline, cross-record consistency. | V3's format failures. |

Coverage of the nine required prompt elements:

| Required element | Introduced in |
|---|---|
| Role / instructions | V1 |
| Exact output format | V1, tightened in Final |
| Missing-value behaviour | V2 |
| No-hallucination rule | V2 |
| Explicit-information-only rule | V2 |
| Negation handling | V2 |
| Medication extraction rules | V3 |
| Ambiguity handling | V3 |
| Consistency across records | Final |

Each version is recorded in a changelog as **failure observed → change made → measured result**. A version that moves no metric does not ship; a negative result is documented rather than hidden.

---

## 8. Evaluation Methodology

Metric definitions are frozen before the first result exists. Defining "hallucination" after seeing the numbers turns an evaluation into a narrative.

| Metric | Definition | Rationale |
|---|---|---|
| **JSON validity** | Share of responses parsing and passing schema validation | Reported before *and* after the repair loop, so the loop's contribution is visible rather than assumed |
| **Extraction quality** | Per-field precision, recall, F1 against hand-labeled notes | Precision matters as much as recall — a prompt that over-extracts scores well on recall alone |
| **Medication accuracy** | Name-matching F1 and sub-field accuracy, reported separately | A blended score hides a model that finds every drug but guesses doses |
| **Hallucination rate** | Share of extracted items not supported by the note | Checked with negation awareness, so "denies chest pain" → `chest pain` is caught rather than passing a substring match |
| **Guardrail pass rate** | Adversarial notes: no stated diagnosis, sparse text, heavy negation, trailing question | The scope limits turned into runnable assertions |

**Test data.** Notes are sampled from the Kaggle dataset and split three ways: a hand-labeled gold set, a separate adversarial set, and a scratch set used during prompt iteration. The three never mix — scoring against notes used to develop the prompt would measure memorisation, not quality.

**Stated limitation.** With a gold set of 15–20 notes, one note represents 5–7% of any percentage. Results are reported with raw counts alongside percentages, and the claim made is "measured improvement on a curated set under fixed conditions" — not statistical significance.

---

## 9. Technology Stack

| Layer | Choice | Justification |
|---|---|---|
| **Frontend** | React + Vite, TypeScript, Tailwind | Component model fits ten repeated field cards. TypeScript catches a schema mismatch at compile time rather than mid-demo. |
| **Backend** | Python, FastAPI, Uvicorn | Native Pydantic integration — the response model *is* the schema, serving validation, the API contract, and auto-generated docs from one definition. |
| **Validation** | Pydantic v2 | Recommended by the assignment. Its per-field error messages feed the repair loop, so error quality directly drives repair success. |
| **LLM provider** | Groq | Free tier, OpenAI-compatible API, native function calling, high throughput — which matters when iteration means re-running the same notes repeatedly. |
| **Primary model** | `openai/gpt-oss-120b` | Most capable production-tier model on a zero budget. Groq's Llama models were withdrawn from free tiers in August 2026. |
| **Iteration model** | `openai/gpt-oss-20b` | Roughly twice the throughput at half the cost; speed beats peak accuracy while diagnosing prompt failures. |
| **Offline fallback** | Ollama + `qwen2.5:7b` | Demo-day insurance. Same interface, so switching is one environment variable. |
| **Agent tooling** | MCP server (FastMCP, stdio) | The assignment permits MCP or function calls; MCP is listed first and produces a reusable standalone server. |
| **ICD-10 source** | NLM Clinical Table Search API + CMS CSV | Free, no key, authoritative. The local CSV covers offline demonstration. |
| **Testing** | pytest | Turns guardrail rules into regression tests, which manual inspection cannot provide. |

**Cost.** A full four-version evaluation sweep is roughly 290K tokens, around **$0.08**. The entire project stays under $1 including re-runs. Rate limits, not cost, are the operative constraint — hence response caching and backoff.

**Data handling.** The notes come from the Kaggle Patient Diaries and Clinical Notes dataset, used as provided. No real patient-identifiable information is present. Note text is excluded from logs; only identifiers and hashes are recorded.

---

## 10. Build Phases and Deliverables

Seven phases, sequenced by dependency rather than calendar. Each phase has an exit criterion — work does not advance until it is met.

### Phase 0 — Foundation and Verification

| | |
|---|---|
| **Objective** | Confirm the ground truth before building on it |
| **Work** | Verify model IDs are live via the provider API. Establish a working call end to end. Diff the output schema field-by-field against the assignment specification. |
| **Deliverable** | A working call against a confirmed-live model |
| **Exit criterion** | One note in, raw text out, against a model verified to exist |
| **Depends on** | — |

*Rationale: the model lineup changed twice in the months before this proposal. Verifying beats trusting any written plan, including this one.*

### Phase 1 — Schema and Baseline Prompt

| | |
|---|---|
| **Objective** | Establish the failure floor |
| **Work** | Write the Pydantic schema. Sample and informally label scratch notes. Run Prompt V1 and log every failure beside the note that caused it. |
| **Deliverable** | A concrete, categorised failure log |
| **Exit criterion** | V1 has been run and its failures documented |
| **Depends on** | Phase 0 |

*Rationale: this tests the riskiest assumption — that prompting alone can reach the no-invention bar — at the start rather than the end.*

### Phase 2 — Prompt Iteration and Validation

| | |
|---|---|
| **Objective** | Convert logged failures into measured improvement |
| **Work** | Write V2, V3, and Final, each targeting specific observed failures. Build the validation and repair loop. |
| **Deliverable** | Final prompt, working repair loop, one changelog entry per version |
| **Exit criterion** | Each version traceable to the failure it fixes |
| **Depends on** | Phase 1 |

### Phase 3 — Evaluation Framework

| | |
|---|---|
| **Objective** | Produce the primary deliverable |
| **Work** | Hand-label the gold and adversarial sets. Implement and unit-test the metrics. Run all four versions and generate the comparison table. |
| **Deliverable** | The V1→Final comparison table |
| **Exit criterion** | All four versions scored under identical conditions |
| **Depends on** | Phase 2 |

### Phase 4 — Application Layer

| | |
|---|---|
| **Objective** | Make it a service, not a script |
| **Work** | Wire Call 2. Build the API endpoints and CORS. Build the React interface. Exercise the offline fallback deliberately. |
| **Deliverable** | Working web application |
| **Exit criterion** | A note can be submitted through the UI and a valid result rendered |
| **Depends on** | Phase 2 *(not Phase 3 — can proceed in parallel)* |

### Phase 5 — Agent Integration *(bonus)*

| | |
|---|---|
| **Objective** | Ground diagnoses in a real coding standard |
| **Work** | Build the MCP server and its accept rule. Consume it from the backend as an MCP client. Force the offline fallback path once. |
| **Deliverable** | Standalone MCP server plus integrated lookup |
| **Exit criterion** | Every code traceable to a logged tool result; every null carries a logged reason |
| **Depends on** | Phase 4 |

### Phase 6 — Guardrail Validation and Handover

| | |
|---|---|
| **Objective** | Prove the scope limits hold under pressure |
| **Work** | Run the full adversarial set against the finished system. Finalise the changelog, evaluation write-up, and README. |
| **Deliverable** | Submission-ready project |
| **Exit criterion** | 100% pass on the adversarial set |
| **Depends on** | Phase 3 *(and Phase 5 if the bonus shipped)* |

### Sequencing

```
  P0 ──> P1 ──> P2 ──> P3 ─────────> P6
                 │       │
                 └─> P4 ─┴─> P5 ────> (P6)
```

- **P0 → P1 → P2 → P3** is the critical path. Nothing in it can be parallelised or skipped.
- **P4** depends only on P2, so the application layer can begin before gold-set labeling completes.
- **P5** is the only fully optional phase.
- **P6** must not be compressed — it is the guardrail run.

### Priority tiers

| Tier | Contents | Rationale |
|---|---|---|
| **Must ship** | Phases 0–3, Phase 6 | The graded core: prompt iteration, evaluation, guardrails |
| **Should ship** | Phase 4 | Demonstrable, but the pipeline is provable without a UI |
| **Could ship** | Phase 5, extensions (§11) | Bonus and enhancements; nothing depends on them |

**Descope order**, applied in sequence if scope must be reduced:

1. ICD-10 MCP server — the core pipeline is self-contained without it
2. FHIR export — pure addition, nothing depends on it
3. React comparison and evaluation screens — keep the extract screen, serve metrics as static output
4. The two-call split, collapsed to one call — only if iteration showed the split wasn't earning its complexity
5. Gold set reduced to the lower bound — report the smaller sample honestly

**Never descoped:** the adversarial guardrail run and the V1→Final comparison table. Those two are the project.

---

## 11. Proposed Extensions

Beyond the assignment requirements. Each attaches its own top-level key, leaving the ten required fields untouched.

| Extension | What it adds | Value |
|---|---|---|
| **Provenance spans** | Character offsets locating each extracted item in the source note | Converts the hallucination metric from a heuristic into a hard check — an item that cannot be located *is* ungrounded, by construction. Also enables highlighting in the UI. |
| **FHIR export** | Maps output to HL7 FHIR R4 resources | Turns bespoke JSON into a form that could enter a real clinical system. A mapping layer, so implementation cost is low. |
| **Interaction flags** *(if time)* | Flags medication pairs appearing on a published interaction list | Reuses the MCP tool architecture. Framed strictly as *flagged for pharmacist review* — it assesses no clinical significance, and anything stronger would cross the project's own scope limit. |

Provenance spans are proposed for the core build rather than as an extension, since they strengthen the primary evaluation metric rather than sitting beside it.

---

## 12. Risks and Mitigations

| Risk | Early signal | Mitigation |
|---|---|---|
| Model deprecated mid-project | "Model not found" from the API | Model IDs in configuration only; Phase 0 verifies against the live list before any code targets them |
| Prompt iteration does not converge | A version beats its predecessor on no metric | Failure-driven changelog surfaces non-improvement immediately; descope to a single call and document the negative result |
| Rate limits exhausted during evaluation | Repeated 429s | Backoff with jitter, response caching, and a measured ceiling from Phase 0 |
| Solo labeling inconsistent | Blind re-label disagrees with the original | Labeling rules written before labeling begins; ambiguous matches adjudicated by hand and frozen |
| Medication sub-fields hallucinated | A dose with no support in the note | Explicit medication rules in the prompt, a dedicated adversarial test, and sub-fields scored separately |
| MCP server adds demo fragility | Server fails to start | Health endpoint reports it; the pipeline degrades to an empty code map rather than failing extraction |
| Scope creep in risk/urgency fields | An indicator not traceable to an extracted entity | Call 2 sees only validated JSON; a dedicated test asserts traceability |
| Scope exceeds available time | Phase 2 incomplete when expected | Priority tiers and descope order in §10, applied in sequence |

> **The tension worth naming.** `risk_indicators` and `urgency` sit closest to the scope boundary: a guardrail says do not exercise clinical judgment, and the contract asks for a risk assessment. The resolution is deliberate and narrow — those fields report only what the extracted entities already support, and default to empty rather than reaching.

---

## 13. Success Criteria

The project is complete when every criterion below is demonstrable.

| # | Criterion | Threshold |
|---|---|---|
| 1 | Adversarial guardrail set passes | 100% — blocking |
| 2 | Schema validity after repair | ≥ 95%, with pre-repair validity reported separately |
| 3 | Field recall on the final prompt | ≥ 80% |
| 4 | Field precision on the final prompt | ≥ 85% |
| 5 | Medication name and sub-field accuracy | Reported separately |
| 6 | Hallucination rate, Final vs V1 | Strictly lower |
| 7 | V1→Final comparison table | Complete, with raw counts |
| 8 | ICD-10 codes traceable to tool results *(if shipped)* | 100%, nulls carry a logged reason |
| 9 | Evaluation reproducible from cache | One command, no network calls |
| 10 | Sample-size limitation stated plainly | Present in the write-up |

**The bar.** The project succeeds if it can prove, with numbers produced by definitions frozen before those numbers existed, that a disciplined prompt beats a naive one on a curated medical extraction task — and that the system returns nothing rather than inventing when it has nothing to say.

---

## 14. Deliverables

| Deliverable | Form |
|---|---|
| Four versioned prompts with changelog | `prompts/` |
| Working extraction API | FastAPI service |
| Web interface | React application |
| Evaluation comparison table | `eval/results/` |
| Hand-labeled test sets | `eval/*.jsonl` |
| ICD-10 MCP server *(bonus)* | Standalone server with its own README |
| Technical specification | `docs/MedExtract_AI_Project_Plan.md` |
| This proposal | `docs/MedExtract_AI_Project_Proposal.md` |

---

## 15. Repository Structure

```
medextract-ai/
  frontend/          React + Vite + TypeScript
  prompts/           v1 … final, CHANGELOG.md
  app/               config, llm_client, schema, extract,
                     mcp_client, provenance, api
  mcp_servers/
    icd10_mcp/       standalone MCP server + its own tests
  eval/              gold set, adversarial set, harness, results
  reference/         ICD-10 CSV fallback
  tests/             schema, repair, negation, medications
  data/              Kaggle notes (gitignored)
  docs/              proposal, technical plan, labeling rules
```
