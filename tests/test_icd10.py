import httpx

from conftest import FakeIcd10Source

from medextract.config import get_settings
from medextract.icd10 import source as source_mod
from medextract.icd10.agent import Icd10Agent
from medextract.icd10.source import Candidate, NlmOnlineSource, get_source
from medextract.icd10.tools import Icd10Tools
from medextract.schemas import ClinicalFact, Evidence, ExtractionResult, Status


def _fact(text, status=Status.PRESENT):
    return ClinicalFact(text=text, status=status, evidence=Evidence(text=text, start=0, end=len(text)))


def source():
    return FakeIcd10Source()


def agent():
    return Icd10Agent(source=source())


# --- agent behavior (deterministic offline fake source) ----------------------
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


def test_resolution_path_is_recorded():
    c = agent().resolve("hypertension", Icd10Tools(source()))
    assert c.resolution_path and c.resolution_path[0].startswith("search:")


def test_coding_is_suggestion_confidence_and_review_present():
    c = agent().resolve("hypertension", Icd10Tools(source()))
    assert 0.0 <= c.confidence <= 1.0
    assert isinstance(c.needs_review, bool)


# --- procedures: online-only means no PCS source -> abstain ------------------
def test_procedures_abstain_no_online_pcs():
    tools = Icd10Tools(source())
    assert tools.supports_pcs is False
    c = agent().resolve("appendectomy", tools, code_type="PCS")
    assert c.code is None and c.needs_review is True
    assert "pcs_unsupported" in c.resolution_path


def test_code_result_procedures_abstain():
    r = ExtractionResult(procedures=[_fact("colonoscopy")])
    codes, _ = agent().code_result(r)
    assert len(codes) == 1
    assert codes[0].code is None and codes[0].needs_review is True


# --- code_result over diagnoses / history ------------------------------------
def test_code_result_skips_negated_and_family():
    r = ExtractionResult(
        diagnosis=[_fact("hypertension", status=Status.NEGATED)],
        medical_history=[_fact("diabetes", status=Status.FAMILY_HISTORY)],
    )
    codes, _ = agent().code_result(r)
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


# --- controllable candidate ranking / rejection (explicit fake) --------------
class _FakeSource:
    supports_pcs = False

    def __init__(self, results, valid_codes):
        self._results = results
        self._valid = {c.upper() for c in valid_codes}
        self.searches = []

    def search(self, query, code_type="CM", limit=5):
        self.searches.append(query)
        return list(self._results.get(query.lower(), []))

    def lookup(self, code):
        return Candidate(code, "desc", 1.0) if code.upper() in self._valid else None

    def validate(self, code):
        return code.upper() in self._valid

    def get_category(self, code):
        return []


def test_strong_candidate_accepted():
    src = _FakeSource({"pneumonia": [Candidate("J18.9", "Pneumonia", 0.95)]}, {"J18.9"})
    c = Icd10Agent(source=src).resolve("pneumonia", Icd10Tools(src))
    assert c.code == "J18.9" and c.needs_review is False
    assert c.resolution_path[-1] == "accept"


def test_multiple_candidates_best_is_selected():
    src = _FakeSource({"sepsis": [
        Candidate("A41.9", "Sepsis, unspecified", 0.93),
        Candidate("A41.50", "Gram-negative sepsis", 0.72),
    ]}, {"A41.9", "A41.50"})
    c = Icd10Agent(source=src).resolve("sepsis", Icd10Tools(src))
    assert c.code == "A41.9"


def test_weak_result_triggers_broader_search():
    src = _FakeSource({
        "acute bronchitis": [Candidate("J20.9", "Acute bronchitis", 0.55)],
        "bronchitis": [Candidate("J40", "Bronchitis", 0.9)],
    }, {"J20.9", "J40"})
    c = Icd10Agent(source=src).resolve("acute bronchitis", Icd10Tools(src))
    assert any("broaden" in p for p in c.resolution_path)


def test_invalid_code_is_rejected_agent_abstains():
    src = _FakeSource({"madeupitis": [Candidate("ZZ.99", "bogus", 0.99)]}, valid_codes=set())
    c = Icd10Agent(source=src).resolve("madeupitis", Icd10Tools(src))
    assert c.code is None and c.needs_review is True
    assert any(p.startswith("validate:ZZ.99:invalid") for p in c.resolution_path)


def test_low_confidence_yields_null_and_needs_review():
    src = _FakeSource({"vague complaint": [Candidate("R69", "Illness unspecified", 0.3)]}, {"R69"})
    c = Icd10Agent(source=src).resolve("vague complaint", Icd10Tools(src))
    assert c.code is None and c.needs_review is True and c.confidence < 0.6


def test_agent_never_invents_code_when_no_candidates():
    src = _FakeSource({}, valid_codes=set())
    c = Icd10Agent(source=src).resolve("anything", Icd10Tools(src))
    assert c.code is None and c.needs_review is True


# --- online source (NLM): hermetic, no real network --------------------------
def _fake_nlm_response(monkeypatch, payload):
    def fake_get(url, params=None, timeout=None):
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))
    monkeypatch.setattr(source_mod.httpx, "get", fake_get)


def test_nlm_search_parses_response(monkeypatch):
    _fake_nlm_response(monkeypatch, [1, ["I10"], None, [["I10", "Essential (primary) hypertension"]]])
    hits = NlmOnlineSource().search("hypertension")
    assert hits and hits[0].code == "I10"
    assert "hypertension" in hits[0].description.lower()


def test_nlm_validate_and_lookup(monkeypatch):
    _fake_nlm_response(monkeypatch, [1, ["E11.9"], None, [["E11.9", "Type 2 diabetes mellitus without complications"]]])
    src = NlmOnlineSource()
    assert src.validate("E11.9") is True
    assert src.lookup("E11.9").code == "E11.9"


def test_nlm_no_pcs():
    # there is no online ICD-10-PCS service -> PCS search returns nothing
    assert NlmOnlineSource().supports_pcs is False
    assert NlmOnlineSource().search("appendectomy", code_type="PCS") == []


def test_nlm_returns_empty_on_network_error_no_fallback(monkeypatch):
    def boom(url, params=None, timeout=None):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(source_mod.httpx, "get", boom)
    # online-only: on failure there is NO local fallback -> empty -> agent abstains
    assert NlmOnlineSource().search("hypertension") == []


def test_get_source_is_online():
    assert isinstance(get_source(), NlmOnlineSource)
    assert isinstance(get_source("nlm"), NlmOnlineSource)
