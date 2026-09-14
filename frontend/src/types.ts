// Mirrors the API's flat response (medextract/brief.py -> to_brief), which is
// the project brief's exact required schema. Evidence offsets / status / meta
// live only inside the backend; they are not sent to the client.

export type Urgency = "low" | "medium" | "high";

export interface Medication {
  name: string;
  dose: string | null;
  frequency: string | null;
  duration: string | null;
}

export interface Icd10Code {
  diagnosis: string;
  code: string | null;
  description: string | null;
  confidence: number;
  needs_review: boolean;
}

export interface ExtractResponse {
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
  icd10_codes: Icd10Code[];
}

export interface ExtractRequest {
  note: string;
  include_icd10: boolean;
  include_summary: boolean;
}

// --- Rich response (POST /extract/rich) --------------------------------------
// The full internal model: every fact keeps its assertion `status` and the
// grounded `evidence` span (with note offsets), so the UI can display the
// backend-validated evidence instead of re-searching the note. ICD-10
// suggestions keep confidence, needs_review, and the agent's resolution_path.

export type FactStatus =
  | "present"
  | "negated"
  | "historical"
  | "family_history"
  | "uncertain";

export type InternalUrgency = "routine" | "elevated" | "urgent";

export interface Evidence {
  text: string;
  start: number | null;
  end: number | null;
}

export interface RichFact {
  text: string;
  status: FactStatus;
  evidence: Evidence;
}

export interface RichMedication {
  name: string;
  dose: string | null;
  frequency: string | null;
  duration: string | null;
  evidence: Evidence;
}

export interface RiskIndicator {
  term: string;
  evidence: Evidence;
}

export interface RichIcd10 {
  source_term: string;
  code: string | null;
  description: string | null;
  code_system: string | null;
  confidence: number;
  needs_review: boolean;
  resolution_path: string[];
}

export interface RichResponse {
  chief_complaint: RichFact | null;
  symptoms: RichFact[];
  diagnosis: RichFact[];
  medical_history: RichFact[];
  medications: RichMedication[];
  procedures: RichFact[];
  follow_up: string | null;
  summary: string | null;
  risk_indicators: RiskIndicator[];
  urgency: InternalUrgency | null;
  icd10_codes: RichIcd10[];
  meta: {
    prompt_version: string;
    model: string;
    repair_attempts: number;
    unsupported_dropped: number;
    incoherent_dropped: number;
    icd10_tool_calls: number;
    latency_ms: number;
  };
}

// Internal urgency -> the badge's low/medium/high vocabulary.
export const URGENCY_MAP: Record<InternalUrgency, Urgency> = {
  routine: "low",
  elevated: "medium",
  urgent: "high",
};
