const TOKEN_KEY = "credit-cabinet-token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(t: string | null) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* хранилище недоступно — вход действует до перезагрузки */
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? "Проверьте заполнение полей" : "Что-то пошло не так";
    throw new ApiError(res.status, message);
  }
  return data as T;
}

export const rub = (n: number | null | undefined) =>
  n == null ? "—" : new Intl.NumberFormat("ru-RU").format(Math.round(n)) + " ₽";

export function annuity(amount: number, ratePct: number, months: number): number {
  const r = ratePct / 100 / 12;
  return r === 0 ? amount / months : (amount * r) / (1 - Math.pow(1 + r, -months));
}

export const TRANSIENT = ["submitted", "checking", "enrichment", "scoring", "decision"];

export type User = { id: number; name: string; role: "client" | "operator" | "analyst" | "admin"; email: string };
