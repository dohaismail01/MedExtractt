import type { RichIcd10 } from "../types";

// Bonus feature (brief §10): each validated diagnosis/procedure mapped to an
// ICD-10 candidate — or an explicit abstention (code: null, needs_review) when
// the agent could not resolve one confidently. Low-confidence suggestions are
// never styled as certain. Each row exposes the agent's audit trail
// (resolution_path) so the coding decision is explainable.

function conf(c: number): string {
  if (c >= 0.8) return "text-emerald-700";
  if (c >= 0.6) return "text-amber-700";
  return "text-slate-500";
}

export default function Icd10Panel({ codes }: { codes: RichIcd10[] }) {
  if (!codes || codes.length === 0) return null;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        ICD-10 suggestions{" "}
        <span className="font-normal text-slate-400">({codes.length})</span>
      </h3>
      <ul className="space-y-2">
        {codes.map((c, i) => {
          const accepted = c.code != null && !c.needs_review;
          return (
            <li key={i} className="rounded-md bg-slate-50 px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-slate-800">{c.source_term}</div>
                  {c.description && (
                    <div className="truncate text-xs text-slate-400">{c.description}</div>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {c.code ? (
                    <span className="rounded bg-sky-100 px-2 py-0.5 font-mono text-xs font-semibold text-sky-800">
                      {c.code}
                    </span>
                  ) : (
                    <span className="rounded bg-slate-200 px-2 py-0.5 text-xs text-slate-500">
                      —
                    </span>
                  )}
                </div>
              </div>

              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                <span className={conf(c.confidence)}>
                  Confidence: {c.confidence.toFixed(2)}
                </span>
                {accepted ? (
                  <span className="font-medium text-emerald-700">Status: Accepted</span>
                ) : (
                  <span className="font-medium text-amber-700">Needs review: Yes</span>
                )}
                {c.code_system && <span className="text-slate-400">{c.code_system}</span>}
              </div>

              {!c.code && (
                <p className="mt-1 text-[11px] text-slate-500">
                  Reason: no sufficiently reliable code match.
                </p>
              )}

              {c.resolution_path.length > 0 && (
                <p className="mt-1 font-mono text-[10px] leading-snug text-slate-400">
                  {c.resolution_path.join("  →  ")}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-[11px] leading-snug text-slate-400">
        Suggestions for clinician review — not billing-ready codes.
      </p>
    </section>
  );
}
