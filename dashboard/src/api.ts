export async function getJSON<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) throw Error("读取失败，请重试");
  return response.json();
}
export async function saveReview(body: unknown) {
  const response = await fetch("/api/reviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = (await response.json()) as { error?: string };
  if (!response.ok) throw Error(data.error || "保存失败");
  return data;
}
