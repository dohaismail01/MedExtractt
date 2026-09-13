// Renders one titled section of extracted string items (symptoms, diagnoses,
// medical history, procedures). The flat API sends plain strings.

export default function FactList({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  if (!items || items.length === 0) return null;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
        <span className="ml-1.5 font-normal text-slate-400">({items.length})</span>
      </h3>
      <div className="flex flex-wrap gap-1.5">
        {items.map((t, i) => (
          <span
            key={i}
            className="rounded-md bg-slate-100 px-2 py-1 text-sm text-slate-700"
          >
            {t}
          </span>
        ))}
      </div>
    </section>
  );
}
