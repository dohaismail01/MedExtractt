"""Evaluate prompt versions against the held-out gold + adversarial sets (Plan §7).

Metrics per version, produced only by the frozen functions in app.normalise and
app.provenance:
  json_valid_pre / post      validity before / after the repair loop
  precision / recall / f1    micro-averaged over the string-list fields
  medication_name_f1         did it find the right drugs (name is the identity key)
  medication_field_accuracy  dose/frequency/duration correct on found drugs
  hallucination_rate         share of extracted items not grounded in the note
  negation_failures          adversarial items that should have been excluded but weren't
  adversarial_pass           share of group-C notes whose assertions hold

Writes eval/results/results.json (served by GET /eval/results).

Run from the project root:
    python -m eval.run_eval                # live calls (cached as it goes)
    python -m eval.run_eval --from-cache   # zero network calls, regenerate table
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app import config, extract, provenance
from app.normalise import matches, normalise
from app.schema import Extraction

GOLD = Path(__file__).parent / "gold_set.jsonl"
ADVERSARIAL = Path(__file__).parent / "adversarial.jsonl"
OUT = config.EVAL_RESULTS_DIR / "results.json"

_LIST_FIELDS = ("symptoms", "diagnosis", "medical_history", "procedures")


def _load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith('{"_comment"'):
            rows.append(json.loads(line))
    return rows


def _greedy_match(pred: list[str], gold: list[str]) -> tuple[int, int, int]:
    """(tp, predicted, gold) with greedy one-to-one assignment via matches()."""
    used = [False] * len(gold)
    tp = 0
    for p in pred:
        for i, g in enumerate(gold):
            if not used[i] and matches(p, g) is True:
                used[i] = True
                tp += 1
                break
    return tp, len(pred), len(gold)


def _score_extraction(pred: Extraction, gold: dict) -> dict:
    tp = pr = gn = 0
    for field in _LIST_FIELDS:
        t, p, g = _greedy_match(getattr(pred, field), gold.get(field, []))
        tp += t
        pr += p
        gn += g

    # Medications: name is the identity key; sub-fields scored on found drugs.
    gold_meds = gold.get("medications", [])
    med_tp = 0
    field_hits = field_total = 0
    used = [False] * len(gold_meds)
    for pm in pred.medications:
        for i, gm in enumerate(gold_meds):
            if not used[i] and pm.name and gm.get("name") and matches(pm.name, gm["name"]) is True:
                used[i] = True
                med_tp += 1
                for sub in ("dose", "frequency", "duration"):
                    field_total += 1
                    pv, gv = getattr(pm, sub), gm.get(sub)
                    if (pv or None) == (gv or None) or (pv and gv and normalise(pv) == normalise(gv)):
                        field_hits += 1
                break

    return {
        "tp": tp, "pred": pr, "gold": gn,
        "med_tp": med_tp, "med_pred": len(pred.medications), "med_gold": len(gold_meds),
        "med_field_hits": field_hits, "med_field_total": field_total,
    }


def _to_extraction(result) -> Extraction:
    return Extraction(**{k: getattr(result, k) for k in Extraction.model_fields})


def evaluate_version(version: str, gold_rows: list[dict], adv_rows: list[dict]) -> dict:
    n = len(gold_rows)
    valid_pre = valid_post = 0
    agg = {"tp": 0, "pred": 0, "gold": 0, "med_tp": 0, "med_pred": 0, "med_gold": 0,
           "med_field_hits": 0, "med_field_total": 0}
    hallucination_total = 0.0

    for row in gold_rows:
        extraction, meta = extract.run_extraction(row["text"], version=version)
        if meta["valid"] and meta["attempts"] == 1:
            valid_pre += 1
        if meta["valid"]:
            valid_post += 1
        s = _score_extraction(extraction, row["labels"])
        for k in agg:
            agg[k] += s[k]
        prov = provenance.build_provenance(row["text"], extraction)
        hallucination_total += provenance.hallucination_rate(prov)

    precision = agg["tp"] / agg["pred"] if agg["pred"] else 0.0
    recall = agg["tp"] / agg["gold"] if agg["gold"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    med_p = agg["med_tp"] / agg["med_pred"] if agg["med_pred"] else 0.0
    med_r = agg["med_tp"] / agg["med_gold"] if agg["med_gold"] else 0.0
    med_f1 = 2 * med_p * med_r / (med_p + med_r) if (med_p + med_r) else 0.0
    med_field_acc = agg["med_field_hits"] / agg["med_field_total"] if agg["med_field_total"] else 1.0

    # Adversarial: full pipeline, check the assertions encoded in labels/tags.
    adv_pass = 0
    negation_failures = 0
    for row in adv_rows:
        result, _ = extract.extract(row["text"], version=version)
        ok, neg_fail = _check_adversarial(result, row)
        adv_pass += int(ok)
        negation_failures += neg_fail

    return {
        "n": n,
        "json_valid_pre": round(valid_pre / n, 3),
        "json_valid_post": round(valid_post / n, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "medication_name_f1": round(med_f1, 3),
        "medication_field_accuracy": round(med_field_acc, 3),
        "hallucination_rate": round(hallucination_total / n, 3),
        "negation_failures": negation_failures,
        "adversarial_pass": f"{adv_pass}/{len(adv_rows)}",
        "counts": {"tp": agg["tp"], "pred": agg["pred"], "gold": agg["gold"]},
    }


def _check_adversarial(result, row: dict) -> tuple[bool, int]:
    """Return (all_assertions_hold, negation_failure_count) for one group-C note."""
    labels = row["labels"]
    ok = True
    neg_fail = 0

    # Every field the gold marks empty must be empty in the output.
    for field in _LIST_FIELDS:
        if not labels.get(field) and getattr(result, field):
            ok = False
    if labels.get("follow_up") is None and result.follow_up:
        ok = False

    # Negation: any symptom the gold excluded that reappears is a negation failure.
    gold_syms = [normalise(s) for s in labels.get("symptoms", [])]
    for s in result.symptoms:
        if normalise(s) not in gold_syms and any(
            cue in row["text"].lower() for cue in ("denies", "no ", "without", "ruled out")
        ):
            # heuristic: an extra symptom on a negation-heavy note
            if "C4" in row.get("tags", []):
                neg_fail += 1
                ok = False

    # C8: a medication dose must not be invented.
    for gm, pm in _zip_meds(labels.get("medications", []), result.medications):
        if gm and gm.get("dose") is None and pm and pm.dose:
            ok = False
    return ok, neg_fail


def _zip_meds(gold_meds, pred_meds):
    out = []
    for i in range(max(len(gold_meds), len(pred_meds))):
        gm = gold_meds[i] if i < len(gold_meds) else None
        pm = pred_meds[i] if i < len(pred_meds) else None
        out.append((gm, pm))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-cache", action="store_true",
                        help="Use only cached responses; error on any cache miss.")
    args = parser.parse_args()
    if args.from_cache:
        config.CACHE_ONLY = True
        config.ENABLE_CACHE = True

    gold_rows = _load(GOLD)
    adv_rows = _load(ADVERSARIAL)
    metrics = {v: evaluate_version(v, gold_rows, adv_rows) for v in config.PROMPT_VERSIONS}
    payload = {
        "available": True,
        "versions": list(config.PROMPT_VERSIONS),
        "gold_n": len(gold_rows),
        "adversarial_n": len(adv_rows),
        "metrics": metrics,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
