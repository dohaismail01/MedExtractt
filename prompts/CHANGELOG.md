# Prompt CHANGELOG

Each version records: **failure observed → change made → measured result.**
A version that moves no metric does not ship. Metrics come from `eval/run_eval.py`
against the held-out `eval/gold_set.jsonl`.

---

## v1 — baseline
**Change made:** Role + bare schema only. No rules, no examples.
**Purpose:** Establish the failure floor so later gains are attributable.
**Failures observed (feed v2):**
- Invents clinically plausible diagnoses not written in the note.
- Includes negated findings ("denies chest pain") as symptoms.
- Uses "N/A" / "none" strings instead of null / [].

_Measured result: (fill in after running eval)_

---

## v2 — guardrails
**Driven by:** v1 failures.
**Change made:** Added no-hallucination rule, explicit-information-only rule,
missing-value behaviour (null / []), and negation handling.
**Failures observed (feed v3):**
- Medications collapsed into one string instead of split name/dose/frequency/duration.
- Uncertain statements ("possible pneumonia") recorded as diagnoses.

_Measured result: (fill in after running eval)_

---

## v3 — medication & ambiguity rules
**Driven by:** v2 failures.
**Change made:** Added medication extraction rules, ambiguity handling
(symptom-vs-diagnosis default), and the worked example from the spec.
**Failures observed (feed final):**
- Inconsistent abbreviation expansion across records (HTN vs hypertension).
- Occasional extra top-level keys / placeholder strings.

_Measured result: (fill in after running eval)_

---

## final — format & consistency enforcement
**Driven by:** v3 failures.
**Change made:** Exact output-format enforcement (no extra keys, no placeholders),
urgency constraint, and cross-record consistency (normalize unambiguous abbreviations,
consistent casing).

_Measured result: (fill in after running eval)_
