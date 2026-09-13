import type { Medication } from "../types";

export default function MedicationTable({ meds }: { meds: Medication[] }) {
  if (!meds || meds.length === 0) return null;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Medications <span className="font-normal text-slate-400">({meds.length})</span>
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-wide text-slate-400">
              <th className="py-1 pr-4 font-medium">Name</th>
              <th className="py-1 pr-4 font-medium">Dose</th>
              <th className="py-1 pr-4 font-medium">Frequency</th>
              <th className="py-1 font-medium">Duration</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {meds.map((m, i) => (
              <tr key={i} className="text-slate-700">
                <td className="py-1.5 pr-4 font-medium">{m.name}</td>
                <td className="py-1.5 pr-4">{m.dose ?? <Dash />}</td>
                <td className="py-1.5 pr-4">{m.frequency ?? <Dash />}</td>
                <td className="py-1.5">{m.duration ?? <Dash />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Dash() {
  return <span className="text-slate-300">—</span>;
}
