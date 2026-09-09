import type { ExtractMeta, MedExtractResult } from "../types";
import FieldCard, { Chips } from "./FieldCard";
import MedicationTable from "./MedicationTable";
import UrgencyBadge from "./UrgencyBadge";

function StatusBar({ meta }: { meta: ExtractMeta }) {
  const s = meta.validationStatus ?? "ok";
  const tone =
    s === "ok" ? "text-emerald-700" : s === "repaired" ? "text-amber-700" : "text-red-700";
  return (
    <div className="mb-4 flex flex-wrap gap-x-6 gap-y-1 text-xs text-subtle">
      <span>
        validation: <span className={`font-medium ${tone}`}>{s}</span>
      </span>
      <span>repair attempts: {meta.repairAttempts ?? "0"}</span>
      <span>model: {meta.modelId ?? "?"}</span>
    </div>
  );
}

export default function ResultPanel({
  result,
  meta,
}: {
  result: MedExtractResult;
  meta: ExtractMeta;
}) {
  const icd = result.icd10_codes ?? {};
  return (
    <div>
      {meta && <StatusBar meta={meta} />}
      <div className="grid gap-3 sm:grid-cols-2">
        <FieldCard label="Chief complaint" isEmpty={!result.chief_complaint}>
          {result.chief_complaint}
        </FieldCard>

        <FieldCard label="Urgency">
          <UrgencyBadge urgency={result.urgency} />
        </FieldCard>

        <FieldCard label="Symptoms" isEmpty={result.symptoms.length === 0}>
          <Chips items={result.symptoms} />
        </FieldCard>

        <FieldCard
          label="Diagnosis"
          isEmpty={result.diagnosis.length === 0}
          emptyHint="no diagnosis stated in this note"
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

        <FieldCard label="Medical history" isEmpty={result.medical_history.length === 0}>
          <Chips items={result.medical_history} />
        </FieldCard>

        <FieldCard label="Procedures" isEmpty={result.procedures.length === 0}>
          <Chips items={result.procedures} />
        </FieldCard>

        <div className="sm:col-span-2">
          <FieldCard label="Medications">
            <MedicationTable meds={result.medications} />
          </FieldCard>
        </div>

        <FieldCard label="Follow-up" isEmpty={!result.follow_up}>
          {result.follow_up}
        </FieldCard>

        <FieldCard
          label="Risk indicators"
          isEmpty={result.risk_indicators.length === 0}
          emptyHint="none flagged"
        >
          <Chips items={result.risk_indicators} />
        </FieldCard>

        <div className="sm:col-span-2">
          <FieldCard label="Summary" isEmpty={!result.summary}>
            {result.summary}
          </FieldCard>
        </div>
      </div>
    </div>
  );
}
