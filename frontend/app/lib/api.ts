export async function api<T = any>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const res = await fetch(`/api${path}`, {
    ...rest,
    headers: { "content-type": "application/json", ...(rest.headers ?? {}) },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
    cache: "no-store",
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : JSON.stringify(data?.detail ?? data));
  return data as T;
}

export const eur = (n: number) => n.toLocaleString("en", { maximumFractionDigits: 2 });

export const fmtDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("ru", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
