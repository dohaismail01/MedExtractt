import { useEffect, useState } from "react";
import { api } from "./api";
import type { ExtractOutcome, Health, PromptVersion } from "./types";
import NoteInput from "./components/NoteInput";
import ResultPanel from "./components/ResultPanel";
import HighlightedNote from "./components/HighlightedNote";
import VersionCompare from "./components/VersionCompare";
import EvalTable from "./components/EvalTable";

type Tab = "extract" | "compare" | "evaluate";

export default function App() {
  const [tab, setTab] = useState<Tab>("extract");
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-ink">MedExtract AI</h1>
        <p className="text-sm text-subtle">
          Clinical notes -&gt; structured medical information. An empty field is a
          correct answer.
        </p>
        <HealthBanner health={health} />
      </header>

      <nav className="mb-6 flex gap-1 border-b border-slate-200">
        {(["extract", "compare", "evaluate"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium capitalize ${
              tab === t
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-subtle hover:text-ink"
            }`}
          >
            {t}
          </button>
        ))}
      </nav>

      {tab === "extract" && <ExtractScreen />}
      {tab === "compare" && <VersionCompare />}
      {tab === "evaluate" && <EvalTable />}
    </div>
  );
}

function HealthBanner({ health }: { health: Health | null }) {
  if (!health) {
    return (
      <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-subtle">
        backend status unknown (is the API running on :8000?)
      </div>
    );
  }
  const ok = health.reachable;
  return (
    <div
      className={`mt-3 rounded-md border px-3 py-1.5 text-xs ${
        ok
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : "border-red-200 bg-red-50 text-red-800"
      }`}
    >
      provider: {health.provider} | model: {health.model} | reachable:{" "}
      {String(ok)}
      {health.mcp_reachable != null && <> | mcp: {String(health.mcp_reachable)}</>}
      {!ok && health.error ? ` | ${health.error}` : ""}
    </div>
  );
}

function ExtractScreen() {
  const [version, setVersion] = useState<PromptVersion>("final");
  const [loading, setLoading] = useState(false);
  const [outcome, setOutcome] = useState<ExtractOutcome | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(text: string) {
    setLoading(true);
    setError(null);
    setNote(text);
    try {
      setOutcome(await api.extract(text, version, true));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setOutcome(null);
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
        <>
          <section>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-subtle">
              Source note (provenance highlighted)
            </h2>
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-sm">
              <HighlightedNote note={note} provenance={outcome.result._provenance} />
            </div>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-subtle">
              Extracted fields
            </h2>
            <ResultPanel result={outcome.result} meta={outcome.meta} />
          </section>
        </>
      )}
    </div>
  );
}
