import type { ReactNode } from "react";

// A single labelled field. Emptiness is rendered explicitly ("not stated in
// note"), never hidden or left blank -- the guardrail made visible.
export default function FieldCard({
  label,
  children,
  emptyHint = "not stated in note",
  isEmpty = false,
}: {
  label: string;
  children?: ReactNode;
  emptyHint?: string;
  isEmpty?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">
        {label}
      </div>
      {isEmpty ? (
        <p className="text-sm italic text-subtle">{emptyHint}</p>
      ) : (
        <div className="text-sm text-ink">{children}</div>
      )}
    </div>
  );
}

// Helper for list fields: chips, or the empty hint.
export function Chips({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((it, i) => (
        <span
          key={i}
          className="rounded-full bg-slate-100 px-2.5 py-0.5 text-sm text-ink"
        >
          {it}
        </span>
      ))}
    </div>
  );
}
