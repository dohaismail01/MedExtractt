// TypeScript mirror of the backend response contract (app/schema.py).
// A schema change on either side becomes a compile error here rather than a
// silent `undefined` at runtime.

export type Urgency = "low" | "medium" | "high";

export interface Medication {
  name: string | null;
  dose: string | null;
  frequency: string | null;
  duration: string | null;
}

export interface MedExtractResult {
  chief_complaint: string | null;
  symptoms: string[];
  diagnosis: string[];
  medical_history: string[];
  medications: Medication[];
  procedures: string[];
  follow_up: string | null;
  summary: string | null;
  risk_indicators: string[];
  urgency: Urgency | null;

  // Extension keys, attached at response assembly (not part of strict validation).
  icd10_codes?: Record<string, string | null>;
  _provenance?: Provenance;
}

export interface ProvenanceItem {
  text: string | null;
  span: [number, number] | null;
  found: boolean;
}

export type Provenance = Record<string, ProvenanceItem[]>;

// Diagnostics returned in response headers, surfaced in the UI.
export interface ExtractMeta {
  validationStatus: string | null;
  repairAttempts: string | null;
  modelId: string | null;
}

export interface ExtractOutcome {
  result: MedExtractResult;
  meta: ExtractMeta;
}

export type PromptVersion = "v1" | "v2" | "v3" | "final";

export interface EvalResults {
  available: boolean;
  message?: string;
  versions?: PromptVersion[];
  gold_n?: number;
  adversarial_n?: number;
  metrics?: Record<PromptVersion, Record<string, unknown>>;
}

export interface Health {
  provider: string;
  model: string;
  configured: boolean;
  reachable: boolean;
  error: string | null;
  icd10_enabled?: boolean;
  icd10_mode?: string;
  mcp_reachable?: boolean | null;
}
