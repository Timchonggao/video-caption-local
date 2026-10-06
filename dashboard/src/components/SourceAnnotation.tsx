import { useEffect, useState } from "react";
import { getJSON } from "../api";
export function SourceAnnotation({ sample }: { sample: string }) {
  const [open, setOpen] = useState(false),
    [value, setValue] = useState<unknown>(null),
    [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    getJSON(`/api/annotations/${sample}`, controller.signal)
      .then(setValue)
      .catch((e) => {
        if (e.name !== "AbortError") setError(String(e));
      });
    return () => controller.abort();
  }, [sample, open]);
  return (
    <details
      className="json-details"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>详细 JSON 字段</summary>
      {open &&
        (error ? (
          <p>{error}</p>
        ) : value === null ? (
          <p>读取中…</p>
        ) : (
          <pre>{JSON.stringify(value, null, 2)}</pre>
        ))}
    </details>
  );
}
