/**
 * Thin client for the FastAPI service.
 *
 * The API owns every business rule and all Mongo writes; this file only moves
 * JSON. Nothing here computes a price, a margin or a total - that lives in
 * calc-engine, behind the API, so the numbers on a quote have one implementation.
 */

export const API_BASE = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Options = RequestInit & { actor?: string };

async function request<T>(path: string, options: Options = {}): Promise<T> {
  const { actor, ...init } = options;
  const url = new URL(path.startsWith("http") ? path : `${API_BASE}${path}`);
  if (actor) url.searchParams.set("actor", actor);

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...init.headers,
      },
      cache: "no-store",
    });
  } catch {
    // A dead API is the single most likely local failure; say so plainly.
    throw new ApiError(
      `Cannot reach the API at ${API_BASE}. Start it with: python -m uvicorn api.main:app --port 8000`,
      503,
    );
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail), response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, actor?: string) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined, actor }),
  patch: <T>(path: string, body: unknown, actor?: string) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body), actor }),
  del: <T>(path: string, actor?: string) => request<T>(path, { method: "DELETE", actor }),
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
};

/** Absolute URL for a document the browser fetches directly (PDF viewer). */
export function documentUrl(code: string, documentId: string): string {
  return `/api/proxy/projects/${code}/documents/${documentId}/file`;
}

export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatMoneyShort(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}
