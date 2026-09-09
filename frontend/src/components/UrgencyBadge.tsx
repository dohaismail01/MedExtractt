import type { Urgency } from "../types";

const STYLES: Record<Urgency, string> = {
  low: "bg-emerald-100 text-emerald-800 border-emerald-200",
  medium: "bg-amber-100 text-amber-800 border-amber-200",
  high: "bg-red-100 text-red-800 border-red-200",
};

export default function UrgencyBadge({ urgency }: { urgency: Urgency | null }) {
  if (!urgency) {
    return <span className="text-sm text-subtle italic">not stated in note</span>;
  }
  return (
    <span
      className={`inline-block rounded-full border px-3 py-0.5 text-sm font-medium capitalize ${STYLES[urgency]}`}
    >
      {urgency}
    </span>
  );
}
