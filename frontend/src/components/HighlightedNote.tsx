import { useMemo } from "react";
import type { ExtractResponse } from "../types";

interface Span {
  start: number;
  end: number;
  kind: "term" | "risk";
}

// The flat API no longer sends evidence offsets, so we locate each extracted
// string in the submitted note by case-insensitive substring search. Risk terms
// are drawn on top in a warmer color. Longer terms are matched first so a term
// isn't swallowed by a shorter overlapping one.
function findSpans(note: string, result: ExtractResponse): Span[] {
  const lower = note.toLowerCase();

  const terms: Array<{ text: string; kind: Span["kind"] }> = [];
  const push = (t: string | null, kind: Span["kind"]) => {
    if (t && t.trim()) terms.push({ text: t.trim(), kind });
  };

  if (result.chief_complaint) push(result.chief_complaint, "term");
  result.symptoms.forEach((t) => push(t, "term"));
  result.diagnosis.forEach((t) => push(t, "term"));
  result.medical_history.forEach((t) => push(t, "term"));
  result.procedures.forEach((t) => push(t, "term"));
  result.medications.forEach((m) => push(m.name, "term"));
  result.risk_indicators.forEach((t) => push(t, "risk"));

  terms.sort((a, b) => b.text.length - a.text.length);

  const spans: Span[] = [];
  const taken: boolean[] = new Array(note.length).fill(false);

  for (const { text, kind } of terms) {
    const needle = text.toLowerCase();
    let from = 0;
    while (true) {
      const idx = lower.indexOf(needle, from);
      if (idx === -1) break;
      const end = idx + needle.length;
      let free = true;
      for (let i = idx; i < end; i++) if (taken[i]) { free = false; break; }
      if (free) {
        for (let i = idx; i < end; i++) taken[i] = true;
        spans.push({ start: idx, end, kind });
      }
      from = idx + needle.length;
    }
  }

  return spans.sort((a, b) => a.start - b.start);
}

export default function HighlightedNote({
  note,
  result,
}: {
  note: string;
  result: ExtractResponse;
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
