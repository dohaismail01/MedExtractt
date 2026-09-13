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
