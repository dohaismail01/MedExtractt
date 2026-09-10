# Labeling Rules

Written **before** labeling begins (Plan §5.1), so gold labels reflect a fixed
policy rather than case-by-case judgement. Every ambiguous decision below has
one ruling; apply it uniformly. Blind re-label 5 notes after 24h and record
self-agreement in the write-up as a stated limitation of solo labeling.

> **Applies to the current gold set.** The gold / adversarial notes in `eval/`
> are **real rows of the Kaggle dataset** with these labels hand-added (labels
> are annotations, not fabricated data). Because that dataset is short
> depression-screening text, the rules most exercised are *symptoms*,
> *diagnosis* (kept empty — mood text is never promoted to a diagnosis), and
> *negation*. The medication, procedure, and history rules below remain valid
> policy but rarely trigger on this dataset.

## General
- Label only what the note **explicitly states**. An empty field is a correct label.
- Never promote a symptom cluster into a diagnosis. `diagnosis` is populated only
  when the note names a diagnosis, impression, or assessment.
- Normalise unambiguous abbreviations to their expansion (HTN → hypertension,
  T2DM → type 2 diabetes mellitus, SOB → shortness of breath). Leave ambiguous
  abbreviations as written.

## Field-by-field
- **chief_complaint** — the presenting complaint as stated. Do not synthesise it
  from the symptom list. If not stated, `null`.
- **symptoms** — stated or observed findings. Exclude anything in a negation scope
  ("denies chest pain", "no fever", "ruled out MI").
- **diagnosis** — named diagnoses only. Uncertain statements ("possible pneumonia",
  "cannot rule out") are **not** diagnoses.
- **medical_history** — conditions framed as past or resolved. A resolved condition
  goes here, never in `symptoms` or `diagnosis`.
- **medications** — one object per drug; `name` is the identity key. Record
  `dose` / `frequency` / `duration` only when stated for that drug, else `null`.
  Discontinued meds ("stopped metformin") are **not** current medications.
- **procedures** — performed or explicitly ordered. Never speculative.
- **follow_up** — stated intent only. Never an invented recommendation.

## Negation scope
A finding is negated if a negation cue (denies, no, without, ruled out, negative,
absent, not, free of, none) appears within 5 tokens before it, not crossing a
clause boundary (`. ; , : but however`). Negated findings are excluded from all lists.

## Match adjudication
Gold-vs-prediction matches scoring 80–89 on `token_set_ratio` go to a manual queue,
are resolved once by hand, and the ruling is frozen into `eval/aliases.jsonl`.
Grounding is judged against the note, never against the gold set.
