import httpx

from medextract.config import get_settings
from medextract.icd10 import source as source_mod
from medextract.icd10.agent import Icd10Agent
from medextract.icd10.source import LocalSqliteSource, NlmOnlineSource, get_source
from medextract.icd10.tools import Icd10Tools
from medextract.schemas import ClinicalFact, Evidence, ExtractionResult, Status


def _fact(text, status=Status.PRESENT):
    return ClinicalFact(text=text, status=status, evidence=Evidence(text=text, start=0, end=len(text)))


def source():
    return LocalSqliteSource()


def agent():
    return Icd10Agent(source=source())


# --- source ---
def test_source_search_exact_alias():
    hits = source().search("hypertension")
    assert hits and hits[0].code == "I10" and hits[0].score >= 0.99


def test_source_validate():
    s = source()
    assert s.validate("I10") is True
    assert s.validate("ZZ.99") is False


def test_source_get_category():
    cat = source().get_category("R07.9")
    codes = {c.code for c in cat}
    assert "R07.9" in codes and "R07.89" in codes  # same R07 family


def test_source_no_pcs():
    assert source().supports_pcs is False
    assert source().search("appendectomy", code_type="PCS") == []


# --- agent ---
def test_resolve_direct_accept():
    tools = Icd10Tools(source())
    c = agent().resolve("hypertension", tools)
    assert c.code == "I10" and c.needs_review is False
    assert c.code_system == "ICD-10-CM"
    assert c.resolution_path[0] == "search:hypertension"
    assert any(p.startswith("validate:I10:ok") for p in c.resolution_path)
    assert c.resolution_path[-1] == "accept"


def test_resolve_alias():
    tools = Icd10Tools(source())
    assert agent().resolve("afib", tools).code == "I48.91"


def test_resolve_broaden_drop_modifier():
    tools = Icd10Tools(source())
    c = agent().resolve("acute myocardial infarction", tools)
    assert c.code == "I21.9"


def test_resolve_abstains_unknown():
    tools = Icd10Tools(source())
    c = agent().resolve("xyzzy nonsense condition", tools)
    assert c.code is None and c.needs_review is True
    assert c.resolution_path[-1] == "abstain"


def test_per_term_call_bound():
    cfg = get_settings()
    tools = Icd10Tools(source())
    c = agent().resolve("some entirely unknown disorder here", tools)
    searches = [p for p in c.resolution_path if p.startswith("search:")]
    assert len(searches) <= cfg.max_icd10_tool_calls_per_term


def test_procedures_pcs_unsupported():
    tools = Icd10Tools(source())
    c = agent().resolve("appendectomy", tools, code_type="PCS")
    assert c.code is None
    assert "pcs_unsupported" in c.resolution_path


def test_code_result_skips_negated_and_family():
    r = ExtractionResult(
        diagnosis=[_fact("hypertension", status=Status.NEGATED)],
        medical_history=[_fact("diabetes", status=Status.FAMILY_HISTORY)],
    )
    codes, calls = agent().code_result(r)
    assert codes == []


def test_code_result_codes_present():
    r = ExtractionResult(diagnosis=[_fact("pneumonia")])
    codes, calls = agent().code_result(r)
    assert len(codes) == 1 and codes[0].code == "J18.9"
    assert calls >= 1


def test_note_ceiling_enforced():
    cfg = get_settings().model_copy(update={"max_icd10_tool_calls_per_note": 2})
    a = Icd10Agent(source=source(), cfg=cfg)
    r = ExtractionResult(diagnosis=[_fact("pneumonia"), _fact("asthma"), _fact("sepsis")])
    _, calls = a.code_result(r)
    assert calls <= 2


# --- online (NLM) source: hermetic, no real network ---
def _fake_nlm_response(monkeypatch, payload):
    """Patch httpx.get to return a canned NLM Clinical Table response."""
    def fake_get(url, params=None, timeout=None):
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))
    monkeypatch.setattr(source_mod.httpx, "get", fake_get)


def test_nlm_search_parses_response(monkeypatch):
    _fake_nlm_response(monkeypatch, [1, ["I10"], None, [["I10", "Essential (primary) hypertension"]]])
    src = NlmOnlineSource()
    hits = src.search("hypertension")
    assert hits and hits[0].code == "I10"
    assert "hypertension" in hits[0].description.lower()


def test_nlm_validate_and_lookup(monkeypatch):
    _fake_nlm_response(monkeypatch, [1, ["E11.9"], None, [["E11.9", "Type 2 diabetes mellitus without complications"]]])
    src = NlmOnlineSource()
    assert src.validate("E11.9") is True
    assert src.lookup("E11.9").code == "E11.9"


def test_nlm_falls_back_to_local_on_network_error(monkeypatch):
    def boom(url, params=None, timeout=None):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(source_mod.httpx, "get", boom)
    src = NlmOnlineSource()  # fallback defaults to LocalSqliteSource
    hits = src.search("hypertension")
    assert hits and hits[0].code == "I10"  # served by the local fallback


def test_get_source_selects_backend():
    assert isinstance(get_source("local_sqlite"), LocalSqliteSource)
    assert isinstance(get_source("nlm"), NlmOnlineSource)
