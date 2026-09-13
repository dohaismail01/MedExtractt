"""Deterministic offline 'LLM'.

Implements the LLMClient protocol without any network. It reads the note out of
the user prompt (the final triple-quoted block) and returns the flat extraction
JSON an instruction-tuned model would produce. This keeps the whole pipeline
and the test-suite hermetic and reproducible. Real extraction quality comes
from configuring a genuine provider; this exists so the system always runs.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

from ..config import Settings

_NOTE_BLOCK = re.compile(r'"""\s*(.*?)\s*"""', re.S)

_SENT_SPLIT = re.compile(r"(?<=[.;\n])\s+|\n+")
NEGATION = ("denies", "denied", "no ", "not ", "without", "negative for", "absent",
            "ruled out", "no evidence of")
HISTORY = ("history of", "h/o", "hx of", "past medical history", "pmh", "status post",
           "s/p", "prior ", "previously")
FAMILY = ("family history", "fhx", "mother", "father", "sister", "brother", "parent",
          "maternal", "paternal", "sibling", "grandmother", "grandfather")
UNCERTAIN = ("possible", "possibly", "likely", "probable", "probably", "suspected",
             "suspect", "r/o", "rule out", "differential", "concern for", "?")

SYMPTOMS = [
    "chest pain", "shortness of breath", "dyspnea", "cough", "fever", "chills",
    "headache", "nausea", "vomiting", "diarrhea", "constipation", "fatigue",
    "dizziness", "palpitations", "abdominal pain", "back pain", "sore throat",
    "rash", "swelling", "weakness", "numbness", "blurred vision", "wheezing",
    "night sweats", "weight loss", "chest tightness", "syncope", "malaise",
]
DIAGNOSES = [
    "hypertension", "type 2 diabetes", "type 1 diabetes", "diabetes", "pneumonia",
    "asthma", "copd", "myocardial infarction", "stroke", "atrial fibrillation",
    "heart failure", "anemia", "depression", "anxiety", "hypothyroidism",
    "hyperlipidemia", "gerd", "migraine", "sepsis", "urinary tract infection",
    "cellulitis", "bronchitis", "angina",
]
PROCEDURES = [
    "ecg", "ekg", "electrocardiogram", "chest x-ray", "ct scan", "mri",
    "echocardiogram", "colonoscopy", "endoscopy", "biopsy", "appendectomy",
    "blood culture", "cbc", "urinalysis", "lumbar puncture", "intubation",
]
MEDICATIONS = [
    "amlodipine", "lisinopril", "metformin", "atorvastatin", "aspirin", "metoprolol",
    "amoxicillin", "azithromycin", "albuterol", "insulin", "omeprazole",
    "levothyroxine", "warfarin", "furosemide", "prednisone", "ibuprofen",
    "acetaminophen", "hydrochlorothiazide", "gabapentin", "clopidogrel", "losartan",
    "simvastatin", "ceftriaxone",
]
_DOSE = re.compile(r"\b(\d+(?:\.\d+)?)\s?(mg|mcg|g|units?|ml|iu)\b", re.I)
_FREQ = re.compile(r"\b(once daily|twice daily|three times daily|daily|nightly|bid|tid|"
                   r"qid|qhs|qd|prn|q\d+h|every \d+ hours?|weekly|as needed)\b", re.I)
_DUR = re.compile(r"\b(?:for )?(\d+\s?(?:day|days|week|weeks|month|months|year|years))\b", re.I)
_CC = ("chief complaint", "presents with", "complains of", "c/o", "here for",
       "presenting with", "reason for visit")
_FU = ("follow up", "follow-up", "f/u", "return to clinic", "rtc", "return in",
       "reassess", "recheck")


def _sentences(text: str) -> List[str]:
    return [p.strip() for p in _SENT_SPLIT.split(text or "") if p and p.strip()]


def _status(ctx: str) -> str:
    c = f" {ctx.lower()} "
    if any(x in c for x in FAMILY):
        return "family_history"
    if any(x in c for x in NEGATION):
        return "negated"
    if any(x in c for x in UNCERTAIN):
        return "uncertain"
    if any(x in c for x in HISTORY):
        return "historical"
    return "present"


def _terms(note: str, sents: List[str], lex: List[str]) -> List[dict]:
    out, seen = [], set()
    low = note.lower()
    for term in sorted(lex, key=len, reverse=True):
        if term not in low or term in seen:
            continue
        if any(term in longer and term != longer for longer in seen):
            continue
        matching = [s for s in sents if term in s.lower()]
        if not matching:
            continue
        # prefer the most descriptive sentence (captures severity/qualifiers)
        ev = max(matching, key=len)
        seen.add(term)
        out.append({"text": term, "status": _status(ev), "evidence": ev})
    return out


def _extract(note: str) -> dict:
    sents = _sentences(note)
    low = note.lower()

    cc: Optional[dict] = None
    for s in sents:
        ls = s.lower()
        for cue in _CC:
            if cue in ls:
                after = s[ls.index(cue) + len(cue):].strip(" :-.")
                cc = {"text": after or s, "evidence": s}
                break
        if cc:
            break

    meds = []
    for name in MEDICATIONS:
        if name not in low:
            continue
        matching = [s for s in sents if name in s.lower()]
        ev = max(matching, key=len) if matching else name
        d, f, du = _DOSE.search(ev), _FREQ.search(ev), _DUR.search(ev)
        meds.append({
            "name": name,
            "dose": d.group(0).strip() if d else None,
            "frequency": f.group(0).strip() if f else None,
            "duration": du.group(1).strip() if du else None,
            "evidence": ev,
        })

    fu = next((s for s in sents if any(c in s.lower() for c in _FU)), None)

    dx_all = _terms(note, sents, DIAGNOSES)
    dx, hx = [], []
    for f in dx_all:
        (hx if f["status"] in ("historical", "family_history") else dx).append(f)

    return {
        "chief_complaint": cc,
        "symptoms": _terms(note, sents, SYMPTOMS),
        "diagnosis": dx,
        "medical_history": hx,
        "medications": meds,
        "procedures": _terms(note, sents, PROCEDURES),
        "follow_up": fu,
    }


class StubClient:
    name = "stub"

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg

    def complete(self, system: str, user: str) -> str:
        blocks = _NOTE_BLOCK.findall(user)
        note = blocks[-1] if blocks else user
        return json.dumps(_extract(note))
