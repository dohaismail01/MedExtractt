import type { Medication } from "../types";

const cell = (v: string | null) =>
  v ? <span>{v}</span> : <span className="text-subtle italic">-</span>;

export default function MedicationTable({ meds }: { meds: Medication[] }) {
  if (meds.length === 0) {
    return <p className="text-sm text-subtle italic">no medications stated in note</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-subtle border-b">
            <th className="py-1 pr-4 font-medium">Name</th>
            <th className="py-1 pr-4 font-medium">Dose</th>
            <th className="py-1 pr-4 font-medium">Frequency</th>
            <th className="py-1 font-medium">Duration</th>
          </tr>
        </thead>
        <tbody>
          {meds.map((m, i) => (
            <tr key={i} className="border-b last:border-0">
              <td className="py-1 pr-4 font-medium">{cell(m.name)}</td>
              <td className="py-1 pr-4">{cell(m.dose)}</td>
              <td className="py-1 pr-4">{cell(m.frequency)}</td>
              <td className="py-1">{cell(m.duration)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
