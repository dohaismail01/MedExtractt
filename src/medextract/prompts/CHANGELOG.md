# Extraction prompt iteration

The project brief requires an explicit prompt-engineering progression
(V1 → V2 → V3 → Final), each version motivated by observed failures, kept so the
improvement can be demonstrated. All versions target the same LLM-facing JSON
shape (facts as `{text, status, evidence}`); the validator grounds `evidence`
against the note and the API then flattens the result to the brief's schema.

Select a version with `MEDEXTRACT_PROMPT_VERSION` (`v1`|`v2`|`v3`|`final`) and
compare them on the identical eval subset (`python -m eval.run_eval
--prompt-version <v>`).

## V1 — baseline
Minimal instructions: extract-only, evidence required, status enum, missing-value
rules, output shape.

**Observed failure modes**
- Status enum listed but not defined → negation/history mislabeled.
- No medication field-splitting guidance → dose/frequency merged into one field.
- No example → structural drift and occasional prose around the JSON.

## V2 — assertion status defined
Adds a physician-facing role, defines each status value with trigger cues, and
tightens the "when in doubt, leave it out" and verbatim-evidence rules.

**Remaining failures**
- Denied findings sometimes dropped entirely instead of emitted as `negated`.
- Medications still under-split; invented frequencies appeared.
- Ambiguous symptom-vs-diagnosis placement inconsistent across notes.
- No worked example to anchor the exact shape.

## V3 — stronger constraints + worked example
Adds explicit **negation/uncertainty**, **medication**, **ambiguity**, and
**consistency** rule blocks, and a one-shot worked example (including a negated
finding and a split medication). Directly targets the V2 failures.

## Final — organized, complete
Same substance as V3, reorganized around the nine elements the brief mandates —
role, explicit-only, no-hallucination, status, negation, medications, ambiguity,
missing-value, consistency, scope — each as a labelled section, plus the worked
example ending with a populated `follow_up`.

**Why Final is better**
- Every required prompt element is a named, checkable section (easier to audit
  and to teach the model), rather than prose the model can skim.
- Failure-driven: the negation, medication, and ambiguity rules exist because V1/V2
  failed on exactly those; the example demonstrates them rather than only stating.
- Consistency rules (lowercasing, dedup, uniform application) reduce record-to-
  record variance, which the brief calls out explicitly.

**How to demonstrate the improvement**
Run each version on the same held-out subset and compare extraction P/R/F1, the
unsupported-extraction (grounding-drop) rate, and first-pass schema validity in
`eval/reports/`. The report table is append-only so regressions stay visible.
Requires a real LLM (e.g. Groq GPT-OSS) — extraction runs on the configured model.
