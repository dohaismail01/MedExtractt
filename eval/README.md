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

Latest stub baseline (reproducible): precision 1.0, recall ~0.78, F1 ~0.88,
ICD-10 top-1 1.0, urgency accuracy ~0.71.

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
