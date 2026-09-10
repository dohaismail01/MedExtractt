import { useEffect, useState } from "react";
import { api } from "./api";
import type { ExtractOutcome, Health, PromptVersion } from "./types";
import NoteInput from "./components/NoteInput";
import ResultPanel from "./components/ResultPanel";
import DatasetLabelCard from "./components/DatasetLabelCard";
import EvalTable from "./components/EvalTable";
import Icd10Panel from "./components/Icd10Panel";

type Tab = "extract" | "evaluate" | "icd10";

export default function App() {
  const [tab, setTab] = useState<Tab>("extract");
  const [health, setHealth] = useState<Health | null>(null);
  const [outcome, setOutcome] = useState<ExtractOutcome | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-6 text-center">
        <h1 className="text-2xl font-bold text-ink">MedExtract AI</h1>
        <p className="text-sm text-subtle">
          Clinical Notes → Structured Medical Information
        </p>
        <HealthBanner health={health} />
      </header>

      <nav className="mb-6 flex justify-center gap-1 border-b border-slate-200">
        {(["extract", "evaluate", "icd10"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              tab === t
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-subtle hover:text-ink"
            }`}
          >
            {t === "icd10" ? "ICD-10" : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </nav>

      {tab === "extract" && (
        <ExtractScreen
          outcome={outcome}
          note={note}
          onResult={(o, n) => {
            setOutcome(o);
            setNote(n);
          }}
        />
      )}
      {tab === "evaluate" && <EvalTable />}
      {tab === "icd10" && <Icd10Panel result={outcome?.result ?? null} />}
    </div>
  );
}

function HealthBanner({ health }: { health: Health | null }) {
  if (!health) {
    return (
      <div className="mx-auto mt-3 max-w-xl rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-subtle">
        backend status unknown (is the API running on :8000?)
      </div>
    );
  }
  const ok = health.reachable;
  return (
    <div
      className={`mx-auto mt-3 max-w-2xl rounded-md border px-3 py-1.5 text-xs ${
        ok
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : "border-red-200 bg-red-50 text-red-800"
      }`}
    >
      provider: {health.provider} · model: {health.model} · reachable: {String(ok)}
      {health.mcp_reachable != null && <> · mcp: {String(health.mcp_reachable)}</>}
      {!ok && health.error ? ` · ${health.error}` : ""}
    </div>
  );
}

function ExtractScreen({
  outcome,
  note,
  onResult,
}: {
  outcome: ExtractOutcome | null;
  note: string;
  onResult: (o: ExtractOutcome | null, note: string) => void;
}) {
  const [version, setVersion] = useState<PromptVersion>("final");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(text: string) {
    setLoading(true);
    setError(null);
    onResult(null, text);
    try {
      onResult(await api.extract(text, version, true), text);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      onResult(null, text);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-6">
      <NoteInput
        onSubmit={submit}
        loading={loading}
        version={version}
        onVersionChange={setVersion}
      />

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {outcome && (
        <div>
          <ResultPanel result={outcome.result} meta={outcome.meta} />
          <DatasetLabelCard note={note} />
        </div>
      )}
    </div>
  );
}
