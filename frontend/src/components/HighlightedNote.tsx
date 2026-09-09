import type { Provenance } from "../types";

// Renders the note with <mark> spans for every grounded provenance item,
// colour-coded by field. A reviewer can audit every extracted value against the
// source in seconds. Ungrounded items (found: false) are listed below as a
// hallucination warning rather than highlighted.
interface Span {
  start: number;
  end: number;
  field: string;
}

export default function HighlightedNote({
  note,
  provenance,
}: {
  note: string;
  provenance?: Provenance;
}) {
  if (!provenance) return <p className="whitespace-pre-wrap">{note}</p>;

  const spans: Span[] = [];
  const ungrounded: { field: string; text: string }[] = [];
  for (const [field, items] of Object.entries(provenance)) {
    for (const it of items) {
      if (it.found && it.span) {
        spans.push({ start: it.span[0], end: it.span[1], field });
      } else if (!it.found && it.text) {
        ungrounded.push({ field, text: it.text });
      }
    }
  }
  spans.sort((a, b) => a.start - b.start);

  // Build non-overlapping segments (skip a span that overlaps an earlier one).
  const parts: Array<{ text: string; field?: string }> = [];
  let cursor = 0;
  for (const s of spans) {
    if (s.start < cursor) continue;
    if (s.start > cursor) parts.push({ text: note.slice(cursor, s.start) });
    parts.push({ text: note.slice(s.start, s.end), field: s.field });
    cursor = s.end;
  }
  if (cursor < note.length) parts.push({ text: note.slice(cursor) });

  return (
    <div>
      <p className="whitespace-pre-wrap leading-relaxed">
        {parts.map((p, i) =>
          p.field ? (
            <mark key={i} className={`prov ${p.field}`} title={p.field}>
              {p.text}
            </mark>
          ) : (
            <span key={i}>{p.text}</span>
          )
        )}
      </p>
      {ungrounded.length > 0 && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm">
          <div className="mb-1 font-semibold text-red-800">
            Ungrounded ({ungrounded.length}) - not located in the note
          </div>
          <ul className="list-disc pl-5 text-red-700">
            {ungrounded.map((u, i) => (
              <li key={i}>
                <span className="font-medium">{u.field}:</span> {u.text}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
