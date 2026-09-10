import { useEffect, useState } from "react";
import { api } from "../api";
import type { EvalResults, PromptVersion } from "../types";

// The metrics rows to display, in order, with friendly labels.
const ROWS: Array<[string, string]> = [
  ["json_valid_pre", "JSON valid (pre-repair)"],
  ["json_valid_post", "JSON valid (post-repair)"],
  ["precision", "Precision"],
  ["recall", "Recall"],
  ["f1", "F1"],
  ["medication_name_f1", "Medication name F1"],
  ["medication_field_accuracy", "Medication field acc."],
  ["hallucination_rate", "Hallucination rate"],
  ["negation_failures", "Negation failures"],
  ["adversarial_pass", "Guardrail pass rate"],
];

// What each prompt version targeted, driven by failures logged from the prior
// one (see prompts/CHANGELOG.md).
const FAILURE_ANALYSIS: Array<[string, string]> = [
  ["V1", "Baseline - role + bare schema, no rules. Establishes the failure floor."],
  ["V2", "No-hallucination, explicit-only, missing-value behaviour, negation handling."],
  ["V3", "Medication sub-fields, ambiguity handling, worked example, delimiters-as-data."],
  ["Final", "Output-format enforcement, urgency constraint, cross-record consistency."],
];

export default function EvalTable() {
  const [data, setData] = useState<EvalResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.evalResults().then(setData).catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="text-sm text-red-700">{error}</p>;
  if (!data) return <p className="text-sm text-subtle">Loading...</p>;
  if (!data.available) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        {data.message ?? "No evaluation results yet."} Run{" "}
        <code className="rounded bg-amber-100 px-1">python -m eval.run_eval</code> to
        generate the table.
      </div>
    );
  }

  const versions = (data.versions ?? []) as PromptVersion[];
  const metrics = data.metrics!;

  return (
    <div>
      <p className="mb-3 text-sm text-subtle">
        Gold set: {data.gold_n} notes | Adversarial: {data.adversarial_n} notes. Every
        figure is produced by definitions frozen before the numbers existed.
      </p>
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-slate-50 text-left">
              <th className="p-3 font-medium">Metric</th>
              {versions.map((v) => (
                <th key={v} className="p-3 font-medium uppercase">
                  {v}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map(([key, label]) => (
              <tr key={key} className="border-b last:border-0">
                <td className="p-3 text-subtle">{label}</td>
                {versions.map((v) => (
                  <td key={v} className="p-3 font-mono">
                    {String((metrics[v] as Record<string, unknown>)?.[key] ?? "-")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="mb-3 mt-8 text-center text-xs font-bold uppercase tracking-widest text-subtle">
        Failure Analysis
      </h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {FAILURE_ANALYSIS.map(([v, desc]) => (
          <div key={v} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
            <span className="mr-2 rounded bg-slate-800 px-1.5 py-0.5 text-xs font-semibold text-white">
              {v}
            </span>
            <span className="text-sm text-ink">{desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
