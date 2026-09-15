# Evaluation

Three complementary harnesses. All run fully offline against the deterministic
`stub` provider by default (set a real LLM to measure a real model).

## 1. Label-free run (real, unlabelled notes)

```bash
python -m eval.prepare_hf_dataset          # build eval/datasets/medical_dialogs_notes.jsonl
python -m eval.run_eval                     # -> eval/reports/
```

Source: HuggingFace `chenhaodev/medical-dialogs-notes` (real clinical notes, **no
gold labels**). Reports only label-free metrics: unsupported-/incoherent-
extraction rate, schema first-pass validity, repair rate, ICD-10 abstention,
mean tool calls, p50/p95 latency. **No P/R/F1** — there are no labels to score
against, and none are invented.

## 2. Labelled subset (P/R/F1)

```bash
MEDEXTRACT_LLM_PROVIDER=stub ICD10_BACKEND=local_sqlite \
  python -m eval.run_eval --dataset eval/datasets/labeled_mini.jsonl
```

`labeled_mini.jsonl` — **30 author-constructed** short notes with gold labels for
symptoms (present/negated), diagnoses, medical history, medications, procedures,
urgency, and selected ICD-10 codes.

> **Provenance / honesty.** These notes were written by the author specifically
> to probe extraction, assertion-status handling and coding. They are **not real
> patient data** and contain no PHI. The labels are the author's, so P/R/F1 here
> measure agreement between the pipeline and those labels on controlled,
> in-vocabulary cases — a floor for behavior, **not** a claim of real-world
> clinical accuracy. Run the same file against a real LLM to score that model.

### Recorded results on `labeled_mini.jsonl`

Two runs of the same 30 notes: the offline `stub` (reproducible, deterministic)
and a real LLM (Groq `openai/gpt-oss-20b`, `ICD10_BACKEND=local_sqlite`, so ICD-10
is scored against the same local gold). The real run paces itself under Groq's
free-tier tokens-per-minute cap via the client's retry/backoff.

| metric | stub | Groq gpt-oss-20b |
|---|---|---|
| precision | 1.000 | 0.819 |
| recall | 0.778 | 0.728 |
| F1 | 0.875 | 0.771 |
| unsupported-extraction rate | 0.000 | 0.069 |
| incoherent-extraction rate | 0.000 | 0.000 |
| schema first-pass validity | 1.000 | 0.967 |
| repair rate | 0.000 | 0.033 |
| ICD-10 top-1 | 1.000 | 0.889 |
| ICD-10 abstention | 0.000 | 0.111 |
| ICD-10 invalid-code rate | 0.000 | 0.000 |
| urgency accuracy | 0.714 | 0.714 |
| latency p50 / p95 (ms) | ~1 / ~2 | 4265 / 54333 |
| failed notes | 0 | 0 |

Reading: on a real model, extraction F1 is ~0.77 and the pipeline is genuinely
exercised — grounding drops ~7% of facts as unsupported (coherence drops none
here), one note needs a repair and recovers, and the ICD-10 agent codes at 0.889
top-1 with 0.111 abstention and **0 invalid codes** (it abstains, never guesses).
The high p95 latency is the rate-limit backoff, not per-call compute.

> Caveat: `labeled_mini` is a 30-note, author-constructed, in-vocabulary set — a
> defensible **floor** on behavior, **not** a real-world clinical-accuracy claim.
> Numbers will vary run to run with a hosted model; regenerate with the command
> above.

## 3. Grounding robustness (the anti-hallucination metric)

```bash
python -m eval.grounding_eval
```

`grounding_adversarial.jsonl` — crafted `{note, injected_LLM_output, expected}`
pairs fed **directly into `ground()`** (no model), isolating the grounding
decision. Half are unsupported facts whose evidence exists in the note but does
not support the claim (e.g. diagnosis "pneumonia" cited to "Patient reports
cough."); half are genuinely supported. Metrics:

- `rejection_rate` — fraction of unsupported facts correctly dropped (target 1.0)
- `retention_rate` — fraction of supported facts correctly kept (target 1.0)
- `false_accept` — unsupported facts wrongly kept (the dangerous error; target 0)
- `false_reject` — supported facts wrongly dropped (recall cost; target 0)

This is the direct measure of the fact↔evidence coherence gate in
`pipeline/validate.py`. A regression test (`tests/test_grounding_eval.py`) locks
it at 1.0 / 1.0 on the curated set.

## Prompt comparison

```bash
python -m eval.compare_prompts             # V1 -> V2 -> V3 -> Final, same dataset
```

The offline stub ignores prompt text, so versions are identical under it (the
harness says so); meaningful deltas require a real LLM.
