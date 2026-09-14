// Renders one titled section of extracted facts. Each fact shows its assertion
// STATUS and the backend-VALIDATED evidence span it was grounded to, so the user
// sees fact -> status -> evidence (per the brief) rather than a bare term.

import type { RichFact, FactStatus } from "../types";

const STATUS_STYLE: Record<FactStatus, string> = {
  present: "bg-sky-100 text-sky-800",
  negated: "bg-slate-200 text-slate-600",
  historical: "bg-violet-100 text-violet-800",
  family_history: "bg-teal-100 text-teal-800",
  uncertain: "bg-amber-100 text-amber-800",
};

const STATUS_LABEL: Record<FactStatus, string> = {
  present: "Present",
  negated: "Negated",
  historical: "Historical",
  family_history: "Family history",
  uncertain: "Uncertain",
};

export default function FactList({
  title,
  items,
}: {
  title: string;
  items: RichFact[];
}) {
  if (!items || items.length === 0) return null;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
        <span className="ml-1.5 font-normal text-slate-400">({items.length})</span>
      </h3>
      <ul className="space-y-2">
        {items.map((f, i) => (
          <li key={i} className="rounded-md bg-slate-50 px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-slate-800">{f.text}</span>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLE[f.status]}`}
              >
                {STATUS_LABEL[f.status]}
              </span>
            </div>
            {f.evidence?.text && (
              <p className="mt-1 border-l-2 border-slate-200 pl-2 text-xs italic text-slate-500">
                “{f.evidence.text}”
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
