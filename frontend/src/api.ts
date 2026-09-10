// Single fetch wrapper to the backend. In dev, Vite proxies /api -> :8000
// (see vite.config.ts), so requests are same-origin and CORS is a non-issue.
import type {
  DatasetLabel,
  EvalResults,
  ExtractOutcome,
  Health,
  MedExtractResult,
  PromptVersion,
} from "./types";

const BASE = "/api";

async function extract(
  note: string,
  version: PromptVersion,
  withProvenance = true
): Promise<ExtractOutcome> {
  const res = await fetch(`${BASE}/extract?version=${version}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note, provenance: withProvenance }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Extraction failed (${res.status}): ${detail}`);
  }
  const result = (await res.json()) as MedExtractResult;
  return {
    result,
    meta: {
      validationStatus: res.headers.get("X-Validation-Status"),
      repairAttempts: res.headers.get("X-Repair-Attempts"),
      modelId: res.headers.get("X-Model-Id"),
    },
  };
}

async function extractFhir(note: string, version: PromptVersion): Promise<unknown> {
  const res = await fetch(`${BASE}/extract?version=${version}&format=fhir`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error(`FHIR export failed (${res.status})`);
  return res.json();
}

async function datasetLabel(note: string): Promise<DatasetLabel> {
  const res = await fetch(`${BASE}/dataset/label`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error(`dataset label ${res.status}`);
  return (await res.json()) as DatasetLabel;
}

async function health(): Promise<Health> {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error(`health ${res.status}`);
  return (await res.json()) as Health;
}

async function evalResults(): Promise<EvalResults> {
  const res = await fetch(`${BASE}/eval/results`);
  return (await res.json()) as EvalResults;
}

export const api = { extract, extractFhir, datasetLabel, health, evalResults };
