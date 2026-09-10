# Approach — MedExtract AI

## Core Requirement (Baseline)

MedExtract AI turns one free-text clinical note into a fixed, validated JSON
object. The baseline is a two-call pipeline with schema validation and a repair
loop:

```
Clinical Note
  → Prompt (versioned V1 → Final)
  → LLM  (Groq, openai/gpt-oss-120b)
  → Structured JSON  (7 extraction fields)
  → Pydantic validation  → repair loop if invalid (capped)
  → Call 2: summary / risk_indicators / urgency  (from validated JSON, NOT the note)
  → Final Response  (10 fields, same shape every time)
```

The output schema is fixed: `chief_complaint`, `symptoms`, `diagnosis`,
`medical_history`, `medications` (`name` / `dose` / `frequency` / `duration`),
`procedures`, `follow_up`, `summary`, `risk_indicators`, `urgency`. Missing
single value → `null`; missing list → `[]`. An empty field is a correct answer —
the system extracts only what the note states and never invents.

---

## Extension 1: Grounded Extraction & Highlighting

**Problem this solves:** "no hallucination" is easy to claim and hard to prove.
A model can return a clinically plausible term that isn't actually in the note,
and a plain string-match check misses negation ("denies chest pain" → `chest
pain` would wrongly pass).

**Approach:**
- For every extracted item, locate it in the source note **in code, after
  extraction** — never by asking the model for character offsets (LLMs count
  characters unreliably).
- Exact case-insensitive search first, then a normalised token-overlap search,
  with a **negation-aware** check (a term inside a negation scope is *not*
  grounded).
- Return `_provenance`: for each item `{ text, span, found }`. `found: false` is
  an ungrounded item by construction.
- The UI renders the note with `<mark>` spans **colour-coded by field**
  (symptoms, diagnosis, medications, …), so a reviewer can audit every value
  against the note in seconds.

**Why it matters for this project specifically:** the whole project is graded on
*refusing to invent*. Provenance turns that from a promise into a visible,
checkable property — you can see exactly which words in the note produced each
field, and which fields have no support.

**Evaluation tie-in:** `hallucination_rate` becomes a hard metric —
`count(found == false) / count(all items)` — not a fuzzy threshold. It is
reported per prompt version and should fall from V1 to Final.

---

## Extension 2: Agentic Orchestration with ICD-10 Lookup (MCP)

**Problem this solves:** a fixed script runs every step blindly. Some steps
aren't always needed (ICD-10 coding only makes sense when a diagnosis exists),
and a model asked for a code from memory will happily hallucinate one.

**Approach:**
- An **LLM-planner agent** (`POST /extract/agent`) is given the note and a tool
  set: `extract_medical_info`, `validate_extraction`, `repair_extraction`,
  `generate_assessment`, `lookup_icd10`, `verify_grounding`, `finish`. The model
  **decides the order** and which tools are needed.
- Conditional tool use is real: `lookup_icd10` is called **only if the
  extraction has a non-empty diagnosis**, and skipped otherwise.
- ICD-10 lookup runs through a standalone **MCP server** (`icd10_mcp`, FastMCP
  over stdio) against the NLM API with a local CMS CSV fallback; FastAPI is the
  MCP client. An in-process function-calling path is the fallback if the server
  can't start.
- Codes are assembled **in code from the tool result**, never from the model's
  own knowledge, and a low-confidence match returns `null` rather than a guess.
- Every run emits an `agent_trace` (the ordered decisions) so the orchestration
  is visible, not hidden.

**Why it matters for this project specifically:** it demonstrates genuine tool
use and decision-making — the model chooses actions based on what it finds —
while staying inside the project's scope limit. The agent only orchestrates the
extraction / validation / lookup workflow; it does not diagnose or make clinical
decisions.

**Evaluation tie-in:** every reported ICD-10 code traces to a logged tool
result (nulls carry a reason), and the agent produces a **quality-control
`qc_confidence`** — a QC signal (schema valid? items grounded? no unsupported
diagnosis?), explicitly not a medical confidence.

---

## How the Two Extensions Combine

The extensions reinforce each other rather than sitting side by side:

- The agent's final **`verify_grounding`** step *is* Extension 1 — it runs the
  provenance check and feeds the result into the QC confidence. So the agentic
  workflow ends with the same hard, negation-aware grounding check the baseline
  metric uses.
- The agent decides to run ICD-10 based on the extracted diagnosis; provenance
  then confirms that diagnosis was actually grounded in the note — so a coded
  diagnosis is both **tool-verified** (real code) and **note-verified** (real
  source text).
- Both are tested the same way: the adversarial guardrail set asserts that
  ungrounded items don't appear and that unsupported diagnoses are never coded.

---

## Summary

| Requirement | Baseline | This Approach |
|---|---|---|
| Fixed 10-field JSON, same shape every note | ✅ | ✅ |
| Schema validation + capped repair loop | ✅ | ✅ |
| Summary/risk/urgency grounded (Call 2 sees validated JSON, not the note) | ✅ | ✅ |
| No-hallucination *proven*, not just claimed | — | ✅ provenance + negation-aware `hallucination_rate` |
| Per-field source highlighting in the UI | — | ✅ colour-coded `<mark>` spans |
| Conditional, decision-based tool use | — | ✅ LLM-planner agent (ICD-10 only if diagnosis) |
| ICD-10 codes from a real tool, never memory | — | ✅ MCP server (NLM + CMS fallback), null over a guess |
| Visible orchestration + quality-control confidence | — | ✅ `agent_trace` + `qc_confidence` |

Further bonuses in the same spirit (attach their own top-level key, leave the 10
fields untouched): **FHIR R4 export** (`?format=fhir`) and **drug interaction
flags** (RxNorm + local ONCHigh table, "flagged for pharmacist review" only).

> Status note: the pipeline, provenance, agent, and MCP paths are implemented;
> the V1 → Final evaluation numbers are produced by running the harness against a
> live model and are **TBD** until that run.
