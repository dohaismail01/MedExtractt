import type { ExtractRequest, ExtractResponse } from "./types";

const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  details?: string[];
  constructor(message: string, status: number, details?: string[]) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

export async function extract(req: ExtractRequest): Promise<ExtractResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${API_URL}. Is the backend running ` +
        `(uvicorn medextract.api.app:app --reload)?`,
      0
    );
  }

  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = undefined;
    }
    if (detail && typeof detail === "object" && "error" in detail) {
      const d = detail as { error: string; details?: string[] };
      throw new ApiError(d.error, res.status, d.details);
    }
    throw new ApiError(
      typeof detail === "string" ? detail : `Request failed (${res.status})`,
      res.status
    );
  }

  return (await res.json()) as ExtractResponse;
}

export async function health(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_URL}/health`);
  if (!res.ok) throw new ApiError("health check failed", res.status);
  return res.json();
}

export { API_URL };
