import { useState } from "react";
import type { ExtractMeta, MedExtractResult } from "../types";
import FieldCard, { Chips } from "./FieldCard";
import MedicationTable from "./MedicationTable";
import UrgencyBadge from "./UrgencyBadge";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 mt-2 text-center text-xs font-bold uppercase tracking-widest text-subtle">
      {children}
    </h2>
  );
}

export default function ResultPanel({
  result,
  meta,
}: {
  result: MedExtractResult;
  meta: ExtractMeta;
}) {
  const [showJson, setShowJson] = useState(false);
  const [copied, setCopied] = useState(false);
  const icd = result.icd10_codes ?? {};

  const jsonText = JSON.stringify(result, null, 2);
  function copy() {
    navigator.clipboard?.writeText(jsonText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  }

  const status = meta.validationStatus ?? "ok";
  const validated = status !== "exhausted";

  return (
    <div>
      {/* ---- EXTRACTION RESULTS ---- */}
      <SectionTitle>Extraction Results</SectionTitle>
      <div className="grid gap-3 sm:grid-cols-2">
        <FieldCard
          label="Chief complaint"
          isEmpty={!result.chief_complaint}
          emptyHint="Not explicitly stated"
        >
          {result.chief_complaint}
        </FieldCard>

        <FieldCard label="Symptoms" isEmpty={result.symptoms.length === 0} emptyHint="None stated">
          <Chips items={result.symptoms} />
        </FieldCard>

        <FieldCard
          label="Diagnosis"
          isEmpty={result.diagnosis.length === 0}
          emptyHint="None stated"
        >
          <div className="flex flex-wrap gap-1.5">
            {result.diagnosis.map((d, i) => (
              <span
                key={i}
                className="rounded-full bg-blue-100 px-2.5 py-0.5 text-sm text-blue-900"
              >
                {d}
                {icd[d] ? (
                  <span className="ml-1 font-mono text-xs text-blue-700">[{icd[d]}]</span>
                ) : null}
              </span>
            ))}
          </div>
        </FieldCard>

        <FieldCard
          label="Medical history"
          isEmpty={result.medical_history.length === 0}
          emptyHint="None stated"
        >
          <Chips items={result.medical_history} />
        </FieldCard>

        <div className="sm:col-span-2">
          <FieldCard label="Medications">
            <MedicationTable meds={result.medications} />
          </FieldCard>
        </div>

        <FieldCard
          label="Procedures"
          isEmpty={result.procedures.length === 0}
          emptyHint="None stated"
        >
          <Chips items={result.procedures} />
        </FieldCard>

        <FieldCard label="Follow-up" isEmpty={!result.follow_up} emptyHint="None stated">
          {result.follow_up}
        </FieldCard>
      </div>

      {/* ---- AI ASSESSMENT ---- */}
      <SectionTitle>AI Assessment</SectionTitle>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <FieldCard label="Summary" isEmpty={!result.summary} emptyHint="Not generated">
            {result.summary}
          </FieldCard>
        </div>

        <FieldCard
          label="Risk indicators"
          isEmpty={result.risk_indicators.length === 0}
          emptyHint="None explicitly stated"
        >
          <Chips items={result.risk_indicators} />
        </FieldCard>

        <FieldCard label="Urgency">
          <UrgencyBadge urgency={result.urgency} />
        </FieldCard>
      </div>

      {result.interaction_flags && result.interaction_flags.length > 0 && (
        <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-800">
            Drug interaction flags
          </div>
          <ul className="space-y-1.5 text-sm">
            {result.interaction_flags.map((f, i) => (
              <li key={i} className="text-amber-900">
                <span className="font-medium">{f.drugs.join(" + ")}</span>{" "}
                <span className="text-amber-700">({f.source}) - {f.status}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-amber-700">
            Flagging only - appears on a published interaction list. Not a clinical
            assessment of significance, dose, or timing.
          </p>
        </div>
      )}

      {/* ---- Validation + JSON ---- */}
      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-slate-200 pt-4">
        <span
          className={`text-sm font-medium ${
            validated ? "text-emerald-700" : "text-red-700"
          }`}
        >
          {validated ? "✓ Schema validated" : "✗ Validation exhausted"}
          {status === "repaired" && (
            <span className="ml-1 font-normal text-subtle">(after repair)</span>
          )}
        </span>
        <span className="text-xs text-subtle">
          repairs: {meta.repairAttempts ?? "0"} · model: {meta.modelId ?? "?"}
        </span>

        <div className="ml-auto flex gap-2">
          <button
            onClick={() => setShowJson((v) => !v)}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-ink hover:bg-slate-50"
          >
            {showJson ? "Hide JSON" : "View JSON"}
          </button>
          <button
            onClick={copy}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-ink hover:bg-slate-50"
          >
            {copied ? "Copied" : "Copy JSON"}
          </button>
        </div>
      </div>

      {showJson && (
        <pre className="mt-3 overflow-x-auto rounded-md bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
          {jsonText}
        </pre>
      )}
    </div>
  );
}
