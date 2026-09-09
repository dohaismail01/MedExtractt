"""Frozen measurement primitives: normalise(), matches(), in_negation_scope().

Every number in the comparison table is produced by exactly these functions,
and they are unit-tested before the first eval run (Plan §7.1–7.3). Without
normalisation a model that writes "shortness of breath" where the note says
"SOB" is scored as both a miss and a hallucination — penalised twice for being
correct. Naive substring grounding is rejected because "denies chest pain" ->
"chest pain" passes it silently, which is the single most important bug.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from . import config

# Whole-string and per-token expansions. Checked-in and extended only between
# eval runs, never mid-run.
ABBREV = {
    "sob": "shortness of breath",
    "htn": "hypertension",
    "t2dm": "type 2 diabetes mellitus",
    "dm": "diabetes mellitus",
    "cp": "chest pain",
    "mi": "myocardial infarction",
    "cad": "coronary artery disease",
    "copd": "chronic obstructive pulmonary disease",
    "cxr": "chest x-ray",
    "ecg": "electrocardiogram",
    "ekg": "electrocardiogram",
    "bid": "twice daily",
    "tid": "three times daily",
    "qd": "once daily",
    "prn": "as needed",
}

STOP = {"the", "a", "an", "of", "with", "and", "to", "for"}

NEG_CUES = {
    "denies", "denied", "no", "without", "negative",
    "ruled", "r/o", "absent", "not", "free", "none",
}
BOUNDARY = {".", ";", ",", "but", "however", ":"}


def normalise(s: str) -> str:
    """Lowercase, expand abbreviations, strip punctuation, drop stopwords,
    naive de-plural. Whole-string expansion is tried before tokenising."""
    s = s.lower().strip()
    s = ABBREV.get(s, s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [ABBREV.get(w, w) for w in s.split() if w not in STOP]
    # Naive de-plural, but leave -ss words intact (shortness, illness).
    toks = [
        w[:-1] if w.endswith("s") and not w.endswith("ss") and len(w) > 3 else w
        for w in toks
    ]
    return " ".join(t for t in toks if t)


def matches(a: str, b: str):
    """True / False / None (None => 80-89 adjudication band, Plan §7.2)."""
    na, nb = normalise(a), normalise(b)
    if na == nb:
        return True
    score = fuzz.token_set_ratio(na, nb)
    if score >= config.FUZZY_MATCH:
        return True
    if score >= config.FUZZY_ADJUDICATE_LOW:
        return None
    return False


def _tokenise_with_offsets(note: str) -> list[tuple[str, int]]:
    """Return (lowercased token, start offset) for word/punct tokens."""
    return [(m.group(0).lower(), m.start()) for m in re.finditer(r"\w+|[.;,:]", note)]


def in_negation_scope(note: str, char_index: int) -> bool:
    """Whether the token at/after char_index sits inside a negation scope,
    scanning back up to NEGATION_WINDOW tokens and stopping at a boundary."""
    toks = _tokenise_with_offsets(note)
    # locate the token index at or after char_index
    idx = next((i for i, (_, off) in enumerate(toks) if off >= char_index), None)
    if idx is None:
        return False
    for back in range(1, config.NEGATION_WINDOW + 1):
        j = idx - back
        if j < 0:
            return False
        tok = toks[j][0]
        if tok in BOUNDARY:
            return False
        if tok in NEG_CUES:
            return True
    return False


def find_grounded_span(note: str, needle: str):
    """Return [start, end] if `needle` is grounded in the note (present and NOT
    negated), else None. Exact case-insensitive search first, then a normalised
    token-overlap check as a fallback locator for the negation test."""
    if not needle:
        return None
    low = note.lower()
    pos = low.find(needle.lower())
    if pos != -1:
        return None if in_negation_scope(note, pos) else [pos, pos + len(needle)]

    # Fallback: locate the head token of the normalised needle for negation test.
    n_norm = normalise(needle)
    if not n_norm:
        return None
    head = n_norm.split()[0]
    pos = low.find(head)
    if pos == -1:
        return None
    if in_negation_scope(note, pos):
        return None
    # Grounded by overlap but no exact span — report presence without offsets.
    return [pos, pos + len(head)]
