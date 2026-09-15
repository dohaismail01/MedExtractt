import { useEffect, useState } from "react";
import { extractRich, health, ApiError, API_URL } from "./api";
import type { RichResponse, RichFact } from "./types";
import { URGENCY_MAP } from "./types";

// A patient positively has a fact only when it is present / historical /
// uncertain. Negated and family_history are excluded from the affirmative
// sections so a denied or a relative's condition never reads as the patient's.
const affirmative = (xs: RichFact[]): RichFact[] =>
  xs.filter(
    (f) => f.status === "present" || f.status === "historical" || f.status === "uncertain"
  );
import HighlightedNote from "./components/HighlightedNote";
import FactList from "./components/FactList";
import MedicationTable from "./components/MedicationTable";
import Icd10Panel from "./components/Icd10Panel";
import UrgencyBadge from "./components/UrgencyBadge";

const SAMPLE = `Patient presents with severe chest pain radiating to the left arm, associated with shortness of breath. Denies fever. History of hypertension and type 2 diabetes. Started on aspirin 81 mg daily and metoprolol. ECG ordered. Follow up in 2 weeks.`;

const FALLBACK_DISCLAIMER =
  "Suggestions for clinician review. Not a diagnostic or triage tool.";

export default function App() {
  const [note, setNote] = useState(SAMPLE);
  // `submitted` is the note that produced the current result, so highlighting
  // stays aligned even if the textarea is edited afterwards.
  const [submitted, setSubmitted] = useState("");
  const [result, setResult] = useState<RichResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ msg: string; details?: string[] } | null>(null);
  const [includeIcd10, setIncludeIcd10] = useState(true);
  const [includeSummary, setIncludeSummary] = useState(true);
  const [disclaimer, setDisclaimer] = useState(FALLBACK_DISCLAIMER);

  // The disclaimer is surfaced via /health (the flat /extract body omits it).
  useEffect(() => {
    health()
      .then((h) => {
        if (typeof h.disclaimer === "string") setDisclaimer(h.disclaimer);
      })
      .catch(() => {
        /* keep fallback disclaimer if the backend is unreachable */
      });
  }, []);

  // Negated findings pulled out of the affirmative sections, shown separately.
  const negated: RichFact[] = result
    ? [...result.symptoms, ...result.diagnosis, ...result.procedures].filter(
        (f) => f.status === "negated"
      )
    : [];

  // Save the current (validated, rich) result as a JSON file the clinician can
  // keep — evidence spans, statuses, and ICD-10 resolution paths included.
  function downloadJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    a.download = `medextract-${stamp}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function onSubmit() {
    if (!note.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extractRich({
        note,
        include_icd10: includeIcd10,
        include_summary: includeSummary,
      });
      setSubmitted(note);
      setResult(res);
    } catch (e) {
      const err = e as ApiError;
      setError({ msg: err.message, details: err.details });
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-4">
        <h1 className="text-2xl font-bold text-slate-900">MedExtract</h1>
        <p className="text-sm text-slate-500">
          Clinical note → structured medical information + ICD-10 suggestions.{" "}
          <span className="text-slate-400">API: {API_URL}</span>
        </p>
      </header>

      <div
        className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
        role="note"
      >
        {disclaimer} Risk/urgency is documentation-based, derived from language in
        the note — it is not triage.
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input column */}
        <div className="space-y-3">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={12}
            placeholder="Paste a clinical note…"
            className="w-full resize-y rounded-lg border border-slate-300 bg-white p-3 text-sm leading-relaxed shadow-sm focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
          />
          <div className="flex flex-wrap items-center gap-4">
            <button
              onClick={onSubmit}
              disabled={loading || !note.trim()}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Extracting…" : "Extract"}
            </button>
            <label className="flex items-center gap-1.5 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={includeIcd10}
                onChange={(e) => setIncludeIcd10(e.target.checked)}
              />
              ICD-10
            </label>
            <label className="flex items-center gap-1.5 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={includeSummary}
                onChange={(e) => setIncludeSummary(e.target.checked)}
              />
              Summary
            </label>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              <p className="font-semibold">{error.msg}</p>
              {error.details && (
                <ul className="mt-1 list-inside list-disc text-xs">
                  {error.details.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {result && <HighlightedNote note={submitted} result={result} />}
        </div>

        {/* Result column */}
        <div className="space-y-4">
          {!result && !loading && (
            <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
              Results will appear here.
            </div>
          )}

          {result && (
            <>
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold text-slate-900">Result</h2>
                <div className="flex items-center gap-2">
                  <UrgencyBadge urgency={result.urgency ? URGENCY_MAP[result.urgency] : null} />
                  <button
                    onClick={downloadJson}
                    title="Download the structured result (evidence, status, ICD-10) as JSON"
                    className="rounded-lg border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-600 shadow-sm transition hover:bg-slate-50"
                  >
                    Save JSON
                  </button>
                </div>
              </div>

              {result.summary && (
                <section className="rounded-lg border border-slate-200 bg-white p-4">
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Summary
                  </h3>
                  <p className="text-sm text-slate-700">{result.summary}</p>
                </section>
              )}

              {result.chief_complaint && (
                <section className="rounded-lg border border-slate-200 bg-white p-4">
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Chief complaint
                  </h3>
                  <p className="text-sm text-slate-700">{result.chief_complaint.text}</p>
                  {result.chief_complaint.evidence?.text && (
                    <p className="mt-1 border-l-2 border-slate-200 pl-2 text-xs italic text-slate-500">
                      “{result.chief_complaint.evidence.text}”
                    </p>
                  )}
                </section>
              )}

              {/* Affirmative sections show only what the patient positively has
                  (present / historical / uncertain). Negated findings are shown
                  separately below so a denied condition never reads as a positive
                  diagnosis; family_history lives under Medical history. Status +
                  evidence are preserved throughout. */}
              <FactList title="Symptoms" items={affirmative(result.symptoms)} />
              <FactList title="Diagnoses" items={affirmative(result.diagnosis)} />
              <FactList title="Medical history" items={result.medical_history} />
              <MedicationTable meds={result.medications} />
              <FactList title="Procedures" items={affirmative(result.procedures)} />
              <FactList title="Denied / ruled out" items={negated} />

              {result.follow_up && (
                <section className="rounded-lg border border-slate-200 bg-white p-4">
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Follow-up
                  </h3>
                  <p className="text-sm text-slate-700">{result.follow_up}</p>
                </section>
              )}

              {result.risk_indicators.length > 0 && (
                <section className="rounded-lg border border-slate-200 bg-white p-4">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Risk indicators
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {result.risk_indicators.map((r, i) => (
                      <span
                        key={i}
                        className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700 ring-1 ring-inset ring-red-600/20"
                      >
                        {r.term}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              {includeIcd10 && <Icd10Panel codes={result.icd10_codes} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
