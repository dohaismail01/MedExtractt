"""MedExtract Agent — an LLM-planner that orchestrates the extraction tools.

The model is given a clinical note and a set of tools, and it decides which to
call and in what order (extract -> validate -> repair if needed -> assessment ->
ICD-10 only if a diagnosis exists -> verify -> finish). Each tool runs
server-side against the existing pipeline components, so the planner sequences
the work but the tools do the real extraction/validation/lookup.

Produces, alongside the final 10-field result:
  - agent_trace: an ordered, human-readable log of every decision and result,
  - verification: which extracted items are grounded in the note,
  - qc_confidence: a QUALITY-CONTROL score (schema valid? items grounded? no
    unsupported diagnosis?) — explicitly NOT a medical/diagnostic confidence.

If the planner errors or stalls, it falls back to the deterministic pipeline so
the endpoint always returns a valid result.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import ValidationError

from . import config, extract, icd10_tool, llm_client, mcp_client, provenance
from .schema import Assessment, Extraction, MedExtractResult

MAX_STEPS = 10

_SYSTEM = """You are a clinical extraction agent. You have tools that extract, \
validate, repair, assess, code, and verify. Use them to turn the clinical note \
into structured data. Follow this policy:

1. Call extract_medical_info first.
2. Call validate_extraction. If it reports errors, call repair_extraction, then \
validate again (at most twice).
3. Call generate_assessment once the extraction is valid.
4. Call lookup_icd10 ONLY if the extraction has a non-empty diagnosis list. If \
diagnosis is empty, skip it — do not call it.
5. Call verify_grounding.
6. Call finish.

Never invent clinical content; the tools do the real work. Call one tool at a time."""

_TOOLS = [
    {"type": "function", "function": {
        "name": "extract_medical_info",
        "description": "Extract the 7 structured fields from the clinical note. Call first.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "validate_extraction",
        "description": "Validate the current extraction against the schema; returns valid or the errors.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "repair_extraction",
        "description": "Repair the current extraction using the last validation errors.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "generate_assessment",
        "description": "Generate summary, risk_indicators, urgency from the validated extraction.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "lookup_icd10",
        "description": "Look up ICD-10 codes for the current diagnosis list. Only call if diagnosis is non-empty.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "verify_grounding",
        "description": "Verify every extracted item is supported by the note; returns grounding + hallucination rate.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Return the final result. Call after extraction is validated, assessed, and verified.",
        "parameters": {"type": "object", "properties": {}},
    }},
]


@dataclass
class AgentState:
    note: str
    version: str
    raw_extraction: Optional[str] = None
    extraction: Optional[Extraction] = None
    errors: Optional[str] = None
    assessment: Optional[Assessment] = None
    icd10: dict = field(default_factory=dict)
    verification: Optional[dict] = None
    trace: list[dict] = field(default_factory=list)

    def log(self, status: str, message: str) -> None:
        self.trace.append({"status": status, "message": message})


# --- ICD-10 resolve (mirror of api._lookup_icd10, kept here to avoid a cycle) ---

def _resolve_icd10(diagnoses: list[str]) -> dict[str, Optional[str]]:
    if not diagnoses:
        return {}
    if config.ICD10_MODE == "mcp":
        try:
            hits = mcp_client.code_diagnoses_mcp(diagnoses)
            return {d: (h["code"] if h else None) for d, h in hits.items()}
        except Exception:  # noqa: BLE001
            pass
    hits = icd10_tool.code_diagnoses(Extraction(diagnosis=diagnoses))
    return {d: (h["code"] if h else None) for d, h in hits.items()}


# --- Tool executors (operate on shared state, return a short string) ---

def _do_extract(s: AgentState) -> str:
    system = extract.load_prompt(s.version)
    user = f"<note>\n{s.note}\n</note>"
    s.raw_extraction = llm_client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=True, max_tokens=config.MAX_TOKENS_CALL1,
    )
    data = llm_client.parse_json(s.raw_extraction)
    n = len(data) if isinstance(data, dict) else 0
    s.log("ok", "Extraction completed")
    return f"Extraction produced JSON with {n} keys."


def _do_validate(s: AgentState) -> str:
    data = llm_client.parse_json(s.raw_extraction or "")
    if data is None:
        s.errors = "Response was not valid JSON."
        s.log("warn", "Validation failed: not JSON")
        return f"invalid: {s.errors}"
    try:
        s.extraction = Extraction.model_validate(data)
        s.errors = None
        dx = ", ".join(s.extraction.diagnosis) or "none"
        s.log("ok", "Schema validated")
        return f"valid. diagnosis: {dx}"
    except ValidationError as exc:
        s.errors = extract._format_validation_error(exc)
        s.log("warn", "Validation reported errors")
        return f"invalid:\n{s.errors}"


def _do_repair(s: AgentState) -> str:
    if not s.errors:
        return "nothing to repair (last validation had no errors)."
    system = extract.load_prompt(s.version)
    user = f"<note>\n{s.note}\n</note>"
    convo = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": s.raw_extraction or ""},
        {"role": "user", "content": extract.load_prompt("repair").format(errors=s.errors)},
    ]
    s.raw_extraction = llm_client.chat(convo, json_mode=True, max_tokens=config.MAX_TOKENS_CALL1)
    s.log("ok", "Repair attempted")
    return "repaired; validate again."


def _do_assessment(s: AgentState) -> str:
    if s.extraction is None:
        return "cannot assess: no valid extraction yet."
    s.assessment = extract.run_assessment(s.extraction)
    s.log("ok", "Assessment generated")
    return f"assessment: urgency={s.assessment.urgency}, risks={len(s.assessment.risk_indicators)}"


def _do_icd10(s: AgentState) -> str:
    if s.extraction is None or not s.extraction.diagnosis:
        s.log("skip", "ICD-10 skipped (no diagnosis)")
        return "skipped: diagnosis is empty."
    s.log("ok", "ICD-10 lookup requested")
    s.icd10 = _resolve_icd10(s.extraction.diagnosis)
    coded = sum(1 for v in s.icd10.values() if v)
    s.log("ok", f"ICD-10 result received ({coded}/{len(s.icd10)} coded)")
    return f"codes: {json.dumps(s.icd10)}"


def _do_verify(s: AgentState) -> str:
    ext = s.extraction or Extraction()
    prov = provenance.build_provenance(s.note, ext)
    rate = provenance.hallucination_rate(prov)
    ungrounded = [
        {"field": f, "text": it["text"]}
        for f, items in prov.items() for it in items if not it["found"]
    ]
    s.verification = {
        "provenance": prov,
        "hallucination_rate": rate,
        "ungrounded": ungrounded,
        "grounded": not ungrounded,
    }
    s.log("ok" if not ungrounded else "warn",
          f"Verification: {len(ungrounded)} ungrounded item(s), hallucination_rate={rate:.2f}")
    return f"hallucination_rate={rate:.2f}, ungrounded={len(ungrounded)}"


_EXECUTORS = {
    "extract_medical_info": _do_extract,
    "validate_extraction": _do_validate,
    "repair_extraction": _do_repair,
    "generate_assessment": _do_assessment,
    "lookup_icd10": _do_icd10,
    "verify_grounding": _do_verify,
}


def _qc_confidence(s: AgentState) -> int:
    """Quality-control confidence (NOT medical). Weighted checks in [0, 100]."""
    checks = []
    checks.append(1.0 if s.extraction is not None else 0.0)          # schema valid
    if s.verification:
        checks.append(1.0 - float(s.verification["hallucination_rate"]))  # grounded fraction
        # no unsupported diagnosis
        dx_ungrounded = any(u["field"] == "diagnosis" for u in s.verification["ungrounded"])
        checks.append(0.0 if dx_ungrounded else 1.0)
    else:
        checks.append(0.0)
        checks.append(0.0)
    # assessment risks trace to extracted content (proxy: assessment produced)
    checks.append(1.0 if s.assessment is not None else 0.0)
    return round(100 * sum(checks) / len(checks))


def _assemble(s: AgentState) -> dict:
    ext = s.extraction or Extraction()
    assessment = s.assessment or Assessment()
    result = MedExtractResult(**ext.model_dump(), **assessment.model_dump())
    payload = result.model_dump()
    if s.icd10:
        payload["icd10_codes"] = s.icd10
    payload["agent_trace"] = s.trace
    payload["qc_confidence"] = _qc_confidence(s)
    if s.verification:
        payload["verification"] = {
            "hallucination_rate": s.verification["hallucination_rate"],
            "ungrounded": s.verification["ungrounded"],
            "grounded": s.verification["grounded"],
        }
        payload["_provenance"] = s.verification["provenance"]
    return payload


def _assistant_msg(msg) -> dict:
    return {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
            for tc in (msg.tool_calls or [])
        ],
    }


def run_agent(note: str, version: str = config.DEFAULT_VERSION) -> dict:
    """Run the LLM-planner agent. Always returns a valid assembled payload."""
    s = AgentState(note=note, version=version)
    if not note or not note.strip():
        s.log("ok", "Empty note — nothing to extract")
        s.extraction = Extraction()
        return _assemble(s)

    s.log("ok", "Clinical note received")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Clinical note:\n<note>\n{note}\n</note>"},
    ]

    try:
        for _ in range(MAX_STEPS):
            msg = llm_client.create_with_backoff(
                model=config.resolved_model(), messages=messages,
                tools=_TOOLS, tool_choice="auto",
                temperature=config.TEMPERATURE, top_p=config.TOP_P,
            ).choices[0].message

            if not msg.tool_calls:
                break

            messages.append(_assistant_msg(msg))
            done = False
            for tc in msg.tool_calls:
                name = tc.function.name
                if name == "finish":
                    done = True
                    result = "finishing."
                else:
                    executor = _EXECUTORS.get(name)
                    result = executor(s) if executor else f"unknown tool {name}"
                messages.append({
                    "role": "tool", "tool_call_id": tc.id, "content": str(result),
                })
            if done:
                break
    except Exception as exc:  # noqa: BLE001 - never fail the request; fall back
        s.log("warn", f"Planner error ({type(exc).__name__}); completing deterministically")
        _fallback(s)

    # Ensure the core steps ran even if the planner skipped some.
    _ensure_complete(s)
    return _assemble(s)


def _ensure_complete(s: AgentState) -> None:
    """Guarantee a validated extraction, assessment, and verification exist."""
    if s.extraction is None:
        if s.raw_extraction is None:
            _do_extract(s)
        _do_validate(s)
        if s.extraction is None:
            _do_repair(s)
            _do_validate(s)
        if s.extraction is None:
            s.extraction = Extraction()
    if s.assessment is None:
        _do_assessment(s)
    if s.verification is None:
        _do_verify(s)


def _fallback(s: AgentState) -> None:
    ext, _ = extract.run_extraction(s.note, s.version)
    s.extraction = ext
    s.assessment = extract.run_assessment(ext)
    if ext.diagnosis:
        s.icd10 = _resolve_icd10(ext.diagnosis)
