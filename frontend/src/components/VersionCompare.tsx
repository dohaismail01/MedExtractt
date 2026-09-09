import { useState } from "react";
import { api } from "../api";
import type { MedExtractResult, PromptVersion } from "../types";

const VERSIONS: PromptVersion[] = ["v1", "v2", "v3", "final"];

// Runs the same note through every prompt version so the improvement is
// watchable live rather than read from a table.
export default function VersionCompare() {
  const [note, setNote] = useState(
    "Patient shows signs of depression, feeling low and fatigued."
  );
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<Partial<Record<PromptVersion, MedExtractResult>>>({});
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    setResults({});
    try {
      const entries = await Promise.all(
        VERSIONS.map(async (v) => [v, (await api.extract(note, v, false)).result] as const)
      );
      setResults(Object.fromEntries(entries));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <textarea
        className="mb-3 h-24 w-full resize-y rounded-md border border-slate-300 p-3 text-sm"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <button
        className="mb-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        disabled={loading || !note.trim()}
        onClick={run}
      >
        {loading ? "Running all versions..." : "Compare V1 -> Final"}
      </button>

      {error && <p className="mb-3 text-sm text-red-700">{error}</p>}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {VERSIONS.map((v) => {
          const r = results[v];
          return (
            <div key={v} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
              <div className="mb-2 text-sm font-semibold uppercase text-subtle">{v}</div>
              {!r ? (
                <p className="text-sm text-subtle italic">
                  {loading ? "..." : "not run"}
                </p>
              ) : (
                <dl className="space-y-1.5 text-sm">
                  <Row label="Symptoms" items={r.symptoms} />
                  <Row label="Diagnosis" items={r.diagnosis} emptyHint="[] (none)" />
                  <Row label="Meds" items={r.medications.map((m) => m.name ?? "?")} />
                  <div>
                    <dt className="text-xs text-subtle">Urgency</dt>
                    <dd>{r.urgency ?? <span className="italic text-subtle">null</span>}</dd>
                  </div>
                </dl>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Row({
  label,
  items,
  emptyHint = "empty",
}: {
  label: string;
  items: string[];
  emptyHint?: string;
}) {
  return (
    <div>
      <dt className="text-xs text-subtle">{label}</dt>
      <dd>
        {items.length === 0 ? (
          <span className="italic text-subtle">{emptyHint}</span>
        ) : (
          items.join(", ")
        )}
      </dd>
    </div>
  );
}
