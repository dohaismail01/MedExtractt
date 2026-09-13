# Baseline eval report (CLAUDE.md §7 step 3)

Reference metrics recorded **before** prompt iteration or agent tuning, so later
changes are measured rather than assumed. Append-only: add new rows below, never
overwrite this one.

- dataset: `eval/datasets/gold_set.jsonl` (5 notes)
- provider: `stub` (deterministic offline extractor)
- prompt_version: `v1`

| metric | value |
|---|---|
| extraction precision | 1.0 |
| extraction recall | 0.947 |
| extraction f1 | 0.973 |
| unsupported_extraction_rate | 0.0 |
| schema_first_pass_validity | 1.0 |
| repair_rate | 0.0 |
| icd10_top1_accuracy | 1.0 |
| icd10_abstention_rate | 0.0 |
| icd10_invalid_code_rate | 0.0 |
| urgency_accuracy | 1.0 |
| latency_ms_p50 | ~1.5 |
| latency_ms_p95 | ~3.9 |
| mean_icd10_tool_calls | 2.8 |

> **Caveat (CLAUDE.md §10):** this gold set overlaps the stub extractor's
> lexicon and is tiny (5 notes), so these numbers are a smoke test, not a claim
> of real-world quality. Re-run with a genuine LLM provider on a held-out,
> non-overlapping annotated set before reporting performance.
