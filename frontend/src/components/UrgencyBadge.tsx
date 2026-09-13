import type { Urgency } from "../types";

const STYLES: Record<Urgency, string> = {
  low: "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
  medium: "bg-amber-100 text-amber-800 ring-amber-600/20",
  high: "bg-red-100 text-red-800 ring-red-600/20",
};

export default function UrgencyBadge({ urgency }: { urgency: Urgency | null }) {
  if (!urgency) return null;
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ring-1 ring-inset ${STYLES[urgency]}`}
      title="Documentation-based, derived from language in the note. Not triage."
    >
      urgency: {urgency}
    </span>
  );
}
