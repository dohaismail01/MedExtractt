"""§9.4 accept rule, exercised offline against the CMS CSV (NLM mocked out)."""
from mcp_servers.icd10_mcp import server


def _force_offline(monkeypatch):
    # Make NLM return nothing so _candidates() falls back to the local CSV.
    monkeypatch.setattr(server, "nlm_search", lambda *a, **k: [])


def test_high_score_accepts_a_code(monkeypatch):
    _force_offline(monkeypatch)
    out = server.icd10_lookup_code("type 2 diabetes mellitus")
    assert out["code"] is not None
    assert out["source"] == "cms_csv"
    assert out["reason"] in ("high_score", "sole_candidate")


def test_no_candidate_returns_null_with_reason(monkeypatch):
    _force_offline(monkeypatch)
    out = server.icd10_lookup_code("asdfqwer nonsense term")
    assert out["code"] is None
    assert out["reason"]  # a null must always carry a logged reason


def test_null_never_guesses(monkeypatch):
    _force_offline(monkeypatch)
    out = server.icd10_lookup_code("xyzzy")
    assert out["code"] is None
