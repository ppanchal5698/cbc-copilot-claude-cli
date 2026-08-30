/** Browser-side fetch helper for the authenticated API proxy. */
import { formatApiDetail } from "@/lib/format";

export class ProxyError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ProxyError";
  }
}

export async function proxyFetcher<T = unknown>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ProxyError(formatApiDetail(detail, response.statusText), response.status);
  }
  return (await response.json()) as T;
}
