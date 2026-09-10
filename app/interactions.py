"""Drug interaction flags (extension, Plan §12.3).

The RxNav Drug Interaction API was discontinued on 2 January 2024. This uses:
  - RxNorm API to normalise a drug string to a canonical RxCUI, and
  - a LOCAL ONCHigh interaction table keyed by RxCUI pairs.

Being local is the advantage: deterministic, auditable, offline, and cannot be
discontinued mid-project. Matching is by RxCUI when RxNorm is reachable, and
falls back to normalised drug name so the check works fully offline.

Framing is deliberate and constrained: this flags a pair as appearing on a
published interaction list. It assesses no clinical significance, dose, route,
timing, or renal function. The status is always "flagged for pharmacist review"
and nothing stronger — anything more would cross the project's scope limit.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from itertools import combinations
from typing import Optional

import httpx

from . import config

_TABLE = config.REFERENCE_DIR / "onchigh_pairs.csv"
_RXNORM_URL = "https://rxnav.nlm.nih.gov/REST/rxcui.json"

STATUS = "flagged for pharmacist review"


def _norm(name: str) -> str:
    return " ".join(name.lower().strip().split())


@lru_cache(maxsize=1)
def _pairs() -> list[dict]:
    """Load the ONCHigh table. Each row: names + RxCUIs for a flagged pair."""
    if not _TABLE.exists():
        return []
    rows: list[dict] = []
    with _TABLE.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append({
                "drug1": _norm(r["drug1"]), "rxcui1": (r.get("rxcui1") or "").strip(),
                "drug2": _norm(r["drug2"]), "rxcui2": (r.get("rxcui2") or "").strip(),
                "source": (r.get("source") or "ONCHigh").strip(),
            })
    return rows


def rxnorm_rxcui(name: str, timeout: float = 6.0) -> Optional[str]:
    """Normalise a drug name to a canonical RxCUI via RxNorm. None on any failure
    (which is expected offline — the name-match path still works)."""
    if not name or not name.strip():
        return None
    try:
        resp = httpx.get(_RXNORM_URL, params={"name": name}, timeout=timeout)
        resp.raise_for_status()
        ids = resp.json().get("idGroup", {}).get("rxnormId", [])
        return ids[0] if ids else None
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return None


def _match(a_name: str, a_rxcui: Optional[str], b_name: str, b_rxcui: Optional[str],
           pair: dict) -> bool:
    """Do meds a and b correspond to the flagged pair, in either order?"""
    def one(name: str, rxcui: Optional[str], slot: int) -> bool:
        pn, pr = pair[f"drug{slot}"], pair[f"rxcui{slot}"]
        return _norm(name) == pn or (bool(rxcui) and rxcui == pr)

    return (one(a_name, a_rxcui, 1) and one(b_name, b_rxcui, 2)) or (
        one(a_name, a_rxcui, 2) and one(b_name, b_rxcui, 1)
    )


def check_interactions(med_names: list[str], use_rxnorm: bool = True) -> list[dict]:
    """Return interaction_flags for every ONCHigh pair present among med_names.

    Each flag: {drugs, rxcuis, source, status}. Empty list when nothing matches.
    """
    names = [n for n in med_names if n and n.strip()]
    if len(names) < 2:
        return []

    rxcui = {n: (rxnorm_rxcui(n) if use_rxnorm else None) for n in names}

    flags: list[dict] = []
    seen: set[frozenset] = set()
    for a, b in combinations(names, 2):
        for pair in _pairs():
            if _match(a, rxcui[a], b, rxcui[b], pair):
                key = frozenset((_norm(a), _norm(b)))
                if key in seen:
                    continue
                seen.add(key)
                flags.append({
                    "drugs": [a, b],
                    "rxcuis": [rxcui[a], rxcui[b]],
                    "source": pair["source"],
                    "status": STATUS,
                })
                break
    return flags
