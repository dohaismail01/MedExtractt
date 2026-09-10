import type { AgentStep, Verification } from "../types";

const ICON: Record<string, string> = {
  ok: "✓",
  warn: "!",
  skip: "→",
};

// Makes the agent's decisions visible: the ordered trace of tool calls, a
// quality-control confidence, and the verification result. The confidence is a
// QC signal (schema valid? items grounded?), NOT a medical/diagnostic score.
export default function AgentActivity({
  trace,
  confidence,
  verification,
}: {
  trace?: AgentStep[];
  confidence?: number;
  verification?: Verification;
}) {
  if (!trace) return null;

  const conf = confidence ?? 0;
  const confTone =
    conf >= 85 ? "text-emerald-700" : conf >= 60 ? "text-amber-700" : "text-red-700";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-bold uppercase tracking-widest text-subtle">
          Agent Activity
        </h2>
        <span className="text-xs text-subtle">
          QC confidence:{" "}
          <span className={`font-semibold ${confTone}`}>{conf}%</span>
        </span>
      </div>

      <ul className="space-y-1">
        {trace.map((step, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span
              className={`mt-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold text-white ${
                step.status === "ok"
                  ? "bg-emerald-500"
                  : step.status === "warn"
                  ? "bg-amber-500"
                  : "bg-slate-400"
              }`}
            >
              {ICON[step.status] ?? "•"}
            </span>
            <span className="text-ink">{step.message}</span>
          </li>
        ))}
      </ul>

      {verification && (
        <div className="mt-3 border-t border-slate-200 pt-3 text-xs">
          <span className={verification.grounded ? "text-emerald-700" : "text-red-700"}>
            {verification.grounded
              ? "✓ All extracted items grounded in the note"
              : `✗ ${verification.ungrounded.length} ungrounded item(s)`}
          </span>
          <span className="ml-2 text-subtle">
            hallucination rate {verification.hallucination_rate.toFixed(2)}
          </span>
          {verification.ungrounded.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-red-700">
              {verification.ungrounded.map((u, i) => (
                <li key={i}>
                  <span className="font-medium">{u.field}:</span> {u.text}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <p className="mt-2 text-[11px] text-subtle">
        QC confidence reflects extraction quality control (schema validity, grounding),
        not medical or diagnostic certainty.
      </p>
    </div>
  );
}
