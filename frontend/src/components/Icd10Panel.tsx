import type { MedExtractResult } from "../types";

// Optional Page 3: diagnosis -> ICD-10 code -> source/tool verification, from
// the most recent extraction. Codes come only from a real tool lookup (MCP
// server or function call); a null code is a correct answer, never a guess.
export default function Icd10Panel({ result }: { result: MedExtractResult | null }) {
  if (!result) {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-subtle">
        Run an extraction on the Extract page first - ICD-10 codes are looked up for
        the diagnoses it finds.
      </div>
    );
  }
  if (result.diagnosis.length === 0) {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-subtle">
        The last extraction found no diagnosis, so there is nothing to code. (For this
        dataset that is the expected, correct result.)
      </div>
    );
  }

  const codes = result.icd10_codes ?? {};
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-slate-50 text-left">
            <th className="p-3 font-medium">Extracted diagnosis</th>
            <th className="p-3 font-medium">ICD-10-CM code</th>
            <th className="p-3 font-medium">Verification</th>
          </tr>
        </thead>
        <tbody>
          {result.diagnosis.map((dx, i) => {
            const code = codes[dx];
            return (
              <tr key={i} className="border-b last:border-0">
                <td className="p-3">{dx}</td>
                <td className="p-3 font-mono">
                  {code ?? <span className="italic text-subtle">no confident match</span>}
                </td>
                <td className="p-3 text-subtle">
                  {code ? "tool lookup (NLM / CMS)" : "null - not guessed"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="p-3 text-xs text-subtle">
        Codes are assembled in code from real tool results, never from the model's own
        knowledge. A null code means no confident match - a correct answer, not a guess.
      </p>
    </div>
  );
}
