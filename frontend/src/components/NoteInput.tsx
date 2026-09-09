import { useState } from "react";
import type { PromptVersion } from "../types";

const SAMPLE =
  "Patient shows signs of depression, feeling low and fatigued.";

export default function NoteInput({
  onSubmit,
  loading,
  version,
  onVersionChange,
  showVersion = true,
}: {
  onSubmit: (note: string) => void;
  loading: boolean;
  version: PromptVersion;
  onVersionChange: (v: PromptVersion) => void;
  showVersion?: boolean;
}) {
  const [note, setNote] = useState("");

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    file.text().then(setNote);
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <textarea
        className="h-40 w-full resize-y rounded-md border border-slate-300 p-3 text-sm outline-none focus:border-blue-400"
        placeholder="Paste a clinical note here..."
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          disabled={loading || !note.trim()}
          onClick={() => onSubmit(note)}
        >
          {loading ? "Extracting..." : "Extract"}
        </button>

        <label className="cursor-pointer text-sm text-blue-700 hover:underline">
          Upload .txt
          <input type="file" accept=".txt" className="hidden" onChange={handleFile} />
        </label>

        <button
          className="text-sm text-subtle hover:underline"
          onClick={() => setNote(SAMPLE)}
        >
          Load sample
        </button>

        {showVersion && (
          <label className="ml-auto flex items-center gap-2 text-sm text-subtle">
            prompt
            <select
              className="rounded-md border border-slate-300 px-2 py-1 text-ink"
              value={version}
              onChange={(e) => onVersionChange(e.target.value as PromptVersion)}
            >
              <option value="v1">V1</option>
              <option value="v2">V2</option>
              <option value="v3">V3</option>
              <option value="final">Final</option>
            </select>
          </label>
        )}
      </div>
    </div>
  );
}
