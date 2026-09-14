# Clinical Note Structured Extractor with ICD-10 Coding Agent

## 1. Objective

MedExtract turns an unstructured clinical note into structured, validated information: chief complaint, symptoms, diagnoses, history, medications, procedures, follow-up, documentation-based risk/urgency indicators, ICD-10 code suggestions, and a short grounded summary.

Risk/urgency indicators reflect language already present in the note (e.g., "severe," "acute," "radiating pain") — they are not a medical triage judgment and should not be read as one.

**Problem:** structuring clinical notes manually is slow and inconsistent. An unconstrained LLM can help, but may invent facts or return unreliable output.

**Core constraint:**
- Extract only what is explicitly present in the note.
- No diagnosis, treatment recommendations, or invented information.
- ICD-10 codes are suggestions for clinician review, not final coding.

**Target users:** physicians and clinical staff who need a fast, checkable structured view of a note.

## 2. Input & Output

**Input:** a free-text clinical note.

**Output:** a consistent structured JSON object. Extracted clinical facts include a `status` and `evidence` span so they can be checked against the original note.

```json
{
  "chief_complaint": {
    "text": null,
    "evidence": null
  },
  "symptoms": [
    {
      "text": "chest pain",
      "status": "present",
      "evidence": "complaining of severe chest pain"
    }
  ],
  "diagnosis": [],
  "medical_history": [],
  "medications": [
    {
      "name": "amlodipine",
      "dose": "5 mg",
      "frequency": "daily",
      "duration": null,
      "evidence": "amlodipine 5 mg daily"
    }
  ],
  "procedures": [],
  "follow_up": null,
  "summary": null,
  "risk_indicators": [],
  "urgency": null,
  "icd10_codes": []
}
```

Status values: `present`, `negated`, `historical`, `family_history`, `uncertain`.

Missing single values → `null`. Missing lists → `[]`.

ICD-10 codes are added only after extraction has been validated. Each `icd10_codes` entry carries the candidate code, a confidence value, and a `needs_review` flag (see Section 5).

## 3. Approach

```
Clinical Note
      ↓
LLM Extraction
      ↓
Validation
      ↓
Retry / Repair if invalid
      ↓
Validated Data
      ↓
ICD-10 Search Agent
      ↓
Code Validation
      ↓
Grounded Summary + Risk Flags
      ↓
Final Output
```

- **LLM Extraction:** extracts information according to the schema and evidence rules.
- **Validation:** checks structure, types, and required fields using Pydantic.
- **Retry / Repair:** re-prompts when validation fails, with a fixed attempt limit.
- **Validated Data:** becomes the source of truth for all downstream stages.
- **ICD-10 Search Agent:** resolves validated diagnoses/procedures to candidate codes.
- **Code Validation:** verifies the selected code before it is returned.
- **Summary + Risk Flags:** generated only from validated structured data. Risk/urgency flags are documentation-based only, not a clinical triage decision.
- **Final Output:** returns the completed structured response.

Keeping downstream stages separate prevents the coding or summary stages from introducing new clinical facts and allows each stage to be evaluated independently.

## 4. Key Design Decisions

- **LLM:** clinical language varies significantly, while a large labeled dataset for a custom extractor is not available. A strong instruction-tuned LLM provides a practical extraction approach.
- **Validation:** ensures malformed or inconsistent output is caught before downstream processing.
- **Evidence grounding:** links extracted facts to the original note, allowing unsupported extractions to be detected and measured.
- **Separate ICD-10 agent:** clinical terms may be abbreviated or different from formal coding terminology. A bounded search agent can try alternative searches while keeping coding separate from clinical extraction.

## 5. ICD-10 Agent

The agent works only on diagnoses and procedures that have already been extracted and validated — it does not extract clinical information itself. This separation is the core justification for calling it agentic: it makes bounded search decisions to resolve an already-validated clinical term into an appropriate ICD-10 candidate, rather than generating the clinical information in the first place.

Diagnoses are coded against ICD-10-CM. Procedures are coded only if the chosen ICD-10 data source supports procedure codes (ICD-10-PCS); if it doesn't, procedures are left uncoded rather than matched against an unsuitable code set.

```
Validated term
      ↓
Direct search
      ↓
Found?
  Yes ↓       No / Ambiguous
 Validate     ↓
  ↓           Broader / hierarchy search
Accept        ↓
/ Review      Validate
              ↓
        Accept / Review / Null
```

- Searches by description first.
- Uses broader or hierarchy searches when needed.
- Validates the final candidate.
- Returns `null` with `needs_review: true` when confidence is insufficient.
- Uses a bounded number of tool calls.
- Records a `resolution_path` for auditing and evaluation.

The agent cannot create, modify, or infer clinical facts.

## 6. Evaluation

Evaluation will run offline against a held-out annotated set of notes.

**Extraction**
- Precision / Recall / F1
- Unsupported extraction rate
- Schema validity rate
- First-pass validity and repair rate

**ICD-10**
- Top-1 accuracy
- Candidate recall
- Abstention / review rate
- Invalid-code rate

**System**
- Average latency per note
- Average ICD-10 tool calls

**Prompt Evaluation**

```
V1 → Evaluate → Identify failures → Improve → V2/V3 → Final
```

All prompt versions will be evaluated on the same data so improvements can be measured rather than assumed.

An optional ablation will compare:

```
LLM only
   ↓
+ Validation
   ↓
+ Retry / Repair
   ↓
+ ICD-10 Agent
```

No performance results are claimed yet; they will be measured after implementation.

## 7. Implementation Plan

1. Prepare dataset and evaluation subset.
2. Build baseline extraction (schema, Prompt V1) and validation/retry-repair.
3. Evaluate the baseline extraction to establish reference metrics before adding more components.
4. Iterate prompts (V2/V3/Final), re-evaluating against the same set.
5. Implement the ICD-10 agent, then evaluate it separately.
6. Add grounded summary and risk flags.
7. Integrate through FastAPI.
8. Run full-system evaluation.
9. Build an optional demo.

## 8. Technology Stack

- Python
- FastAPI
- Pydantic
- LLM: candidate models include Llama 3.3 70B, Qwen 2.5 72B, and smaller local models through Ollama.
- Agent: custom tool-calling loop for ICD-10 search and validation.

The final model will be selected based on extraction quality, structured-output reliability, latency, available resources, and API limits.

## 9. Risks & Limitations

- Public/synthetic data may not represent real clinical note variability.
- Prompting and evidence grounding reduce hallucination but do not eliminate it.
- Negation, uncertainty, and ambiguous terminology can still cause extraction errors.
- ICD-10 terms may have multiple plausible codes.
- Free-tier API limits may affect throughput.
- The system is not intended for real clinical deployment without additional safety, privacy, security, and validation requirements.

## 10. Future Improvements

- Semantic/embedding-based ICD-10 search.
- ML-based urgency classification with sufficient labeled data.
- OCR for scanned notes.
- ICD-10 result caching and parallel processing.
- Evaluation on more diverse datasets.
