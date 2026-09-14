import { useMemo } from "react";
import type { RichResponse, Evidence } from "../types";

interface Span {
  start: number;
  end: number;
  kind: "term" | "risk";
}

// Highlighting is driven by the backend-VALIDATED evidence offsets. Every
// grounded fact carries an `evidence` span; when the validator located it
// exactly it also carries {start,end} in the note's index space, which we use
// directly. Only when offsets are absent (a fuzzy-matched span) do we fall back
// to a case-insensitive substring search for that evidence text. This means the
// UI highlights what the backend actually accepted, not what a naive re-search
// of the extracted term happens to find.
function findSpans(note: string, result: RichResponse): Span[] {
  const lower = note.toLowerCase();
  const taken: boolean[] = new Array(note.length).fill(false);
  const spans: Span[] = [];

  const claim = (start: number, end: number, kind: Span["kind"]): boolean => {
    if (start < 0 || end > note.length || start >= end) return false;
    for (let i = start; i < end; i++) if (taken[i]) return false;
    for (let i = start; i < end; i++) taken[i] = true;
    spans.push({ start, end, kind });
    return true;
  };

  const place = (ev: Evidence | undefined, kind: Span["kind"]) => {
    if (!ev || !ev.text) return;
    // 1) exact offsets from the validator
    if (ev.start != null && ev.end != null && note.slice(ev.start, ev.end)) {
      if (claim(ev.start, ev.end, kind)) return;
    }
    // 2) fallback: locate the validated evidence text (not the extracted term)
    const idx = lower.indexOf(ev.text.toLowerCase());
    if (idx !== -1) claim(idx, idx + ev.text.length, kind);
  };

  // risk spans first (drawn on top, warmer color), then facts.
  result.risk_indicators.forEach((r) => place(r.evidence, "risk"));
  if (result.chief_complaint) place(result.chief_complaint.evidence, "term");
  result.symptoms.forEach((f) => place(f.evidence, "term"));
  result.diagnosis.forEach((f) => place(f.evidence, "term"));
  result.medical_history.forEach((f) => place(f.evidence, "term"));
  result.procedures.forEach((f) => place(f.evidence, "term"));
  result.medications.forEach((m) => place(m.evidence, "term"));

  return spans.sort((a, b) => a.start - b.start);
}

export default function HighlightedNote({
  note,
  result,
}: {
  note: string;
  result: RichResponse;
}) {
  const parts = useMemo(() => {
    const spans = findSpans(note, result);
    const out: Array<{ text: string; kind: Span["kind"] | null }> = [];
    let cursor = 0;
    for (const s of spans) {
      if (s.start < cursor) continue;
      if (s.start > cursor) out.push({ text: note.slice(cursor, s.start), kind: null });
      out.push({ text: note.slice(s.start, s.end), kind: s.kind });
      cursor = s.end;
    }
    if (cursor < note.length) out.push({ text: note.slice(cursor), kind: null });
    return out;
  }, [note, result]);

  return (
    <div className="whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-white p-4 text-sm leading-relaxed">
      {parts.map((p, i) =>
        p.kind === "term" ? (
          <mark key={i} className="rounded bg-sky-100 px-0.5 text-sky-900">
            {p.text}
          </mark>
        ) : p.kind === "risk" ? (
          <mark key={i} className="rounded bg-red-100 px-0.5 font-semibold text-red-900">
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        )
      )}
    </div>
  );
}
