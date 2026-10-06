import { useEffect, useState } from "react";
import { getJSON } from "../api";
import type { Data, Inventory } from "../types";
export function useDashboard(sample?: string) {
  const [data, setData] = useState<Data | null>(null),
    [error, setError] = useState(""),
    [inventory, setInventory] = useState<Inventory | null>(null);
  async function reload() {
    try {
      setData(await getJSON<Data>("/api/clips"));
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    reload();
  }, []);
  useEffect(() => {
    setInventory(null);
    if (!sample) return;
    const controller = new AbortController();
    getJSON<Inventory>(`/api/sample-details/${sample}`, controller.signal)
      .then(setInventory)
      .catch((e) => {
        if (e.name !== "AbortError") setError(String(e));
      });
    return () => controller.abort();
  }, [sample]);
  return { data, error, inventory, reload };
}
