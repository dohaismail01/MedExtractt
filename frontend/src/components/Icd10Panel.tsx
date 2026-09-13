import type { Icd10Code } from "../types";

// Bonus feature (brief §10): each extracted diagnosis mapped to an ICD-10 code,
// or null when the agent could not confidently resolve one (needs_review).
export default function Icd10Panel({ codes }: { codes: Icd10Code[] }) {
  if (!codes || codes.length === 0) return null;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        ICD-10 suggestions{" "}
        <span className="font-normal text-slate-400">({codes.length})</span>
      </h3>
      <ul className="space-y-2">
        {codes.map((c, i) => (
          <li
            key={i}
            className="flex items-start justify-between gap-3 rounded-md bg-slate-50 px-3 py-2"
          >
            <div className="min-w-0">
              <div className="text-sm text-slate-700">{c.diagnosis}</div>
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
                  no code
                </span>
              )}
              {c.needs_review && (
                <span
                  className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800"
                  title={`confidence ${c.confidence.toFixed(2)}`}
                >
                  review
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] leading-snug text-slate-400">
        Suggestions for clinician review — not billing-ready codes.
      </p>
    </section>
  );
}
