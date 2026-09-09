"""FastAPI endpoints + CORS (Plan §10).

    POST /extract              run the pipeline, return the validated 10-field JSON
    POST /extract?format=fhir  same pipeline, serialised as a FHIR R4 Bundle
    GET  /health               provider + MCP reachability, resolved model
    GET  /eval/results         stored evaluation metrics for the comparison table

Diagnostics ride in response headers (X-Validation-Status, X-Repair-Attempts,
X-Model-Id), so the body stays exactly ten fields. Extension keys (icd10_codes,
_provenance) are attached to the serialised dict at assembly, never as schema
fields — strict validation always runs against the mandated contract.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import config, extract, fhir_export, icd10_tool, llm_client, mcp_client, provenance
from .schema import Extraction

app = FastAPI(title="MedExtract AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractRequest(BaseModel):
    note: str = Field(..., description="The raw clinical note text.")
    provenance: bool = Field(False, description="Attach the _provenance mapping.")


def _lookup_icd10(diagnoses: list[str]) -> dict[str, Optional[str]]:
    """ICD-10 codes for the diagnosis list. MCP server first (Plan §9), with the
    in-process function-calling tool as a graceful fallback."""
    if not diagnoses:
        return {}
    if config.ICD10_MODE == "mcp":
        try:
            hits = mcp_client.code_diagnoses_mcp(diagnoses)
            return {dx: (h["code"] if h else None) for dx, h in hits.items()}
        except Exception:  # noqa: BLE001 - fall back to function calling
            pass
    hits = icd10_tool.code_diagnoses(Extraction(diagnosis=diagnoses))
    return {dx: (h["code"] if h else None) for dx, h in hits.items()}


@app.get("/health")
def health() -> dict:
    info = llm_client.health()
    info["icd10_enabled"] = config.ENABLE_ICD10
    info["icd10_mode"] = config.ICD10_MODE
    info["mcp_reachable"] = (
        mcp_client.mcp_reachable() if config.ICD10_MODE == "mcp" else None
    )
    return info


@app.post("/extract")
def post_extract(
    req: ExtractRequest,
    version: str = Query(config.DEFAULT_VERSION),
    format: Optional[str] = Query(None, description="Set to 'fhir' for a FHIR Bundle."),
):
    if version not in config.PROMPT_VERSIONS:
        raise HTTPException(400, f"version must be one of {config.PROMPT_VERSIONS}")
    if len(req.note) > config.NOTE_MAX_CHARS:
        raise HTTPException(413, f"note exceeds NOTE_MAX_CHARS ({config.NOTE_MAX_CHARS})")

    result, meta = extract.extract(req.note, version=version)

    # Call 3 (bonus): ICD-10 codes, attached at assembly, outside strict validation.
    icd10_codes: dict = {}
    payload = result.model_dump()
    if config.ENABLE_ICD10 and result.diagnosis:
        icd10_codes = _lookup_icd10(result.diagnosis)
        payload["icd10_codes"] = icd10_codes

    if req.provenance:
        extraction = Extraction(**{k: getattr(result, k) for k in Extraction.model_fields})
        payload["_provenance"] = provenance.build_provenance(req.note, extraction)

    if format == "fhir":
        return fhir_export.to_fhir_bundle(result, icd10_codes=icd10_codes)

    return JSONResponse(
        content=payload,
        headers={
            "X-Validation-Status": meta.get("status", "ok"),
            "X-Repair-Attempts": str(max(0, meta.get("attempts", 1) - 1)),
            "X-Model-Id": config.resolved_model(),
        },
    )


@app.get("/eval/results")
def eval_results() -> dict:
    """Serve the stored evaluation metrics, if run_eval has produced them."""
    path = config.EVAL_RESULTS_DIR / "results.json"
    if not path.exists():
        return {"available": False, "message": "Run eval/run_eval.py to generate metrics."}
    return json.loads(path.read_text(encoding="utf-8"))
