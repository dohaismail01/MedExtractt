import { useEffect, useState } from "react";
import { api } from "../api";
import type { DatasetLabel } from "../types";

// The Kaggle classification label (depression / no depression), shown SEPARATELY
// from the 10-field extraction. It is a dataset target, not an extraction field,
// so it never enters the extraction contract.
export default function DatasetLabelCard({ note }: { note: string }) {
  const [data, setData] = useState<DatasetLabel | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .datasetLabel(note)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, [note]);

  // Only render when the dataset is present AND this note is a dataset row.
  if (!data || !data.available || !data.matched) return null;

  return (
    <div className="mt-6 border-t border-dashed border-slate-300 pt-4">
      <h2 className="mb-2 text-center text-xs font-bold uppercase tracking-widest text-subtle">
        Dataset Label
      </h2>
      <div className="mx-auto max-w-sm rounded-lg border border-violet-200 bg-violet-50 p-4 text-center">
        <div className="text-lg font-semibold capitalize text-violet-900">
          {data.label}
        </div>
        <p className="mt-1 text-xs text-violet-700">
          Kaggle classification target - separate from the extraction, shown for
          reference only.
        </p>
      </div>
    </div>
  );
}
