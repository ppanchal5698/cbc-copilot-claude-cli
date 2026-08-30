/** Shared secret between the Next.js server and the FastAPI service. */
const DEV_SECRET = "cbc-local-dev-key-change-me";
const DEV_AUTH_SECRET = "cbc-opshub-local-dev-secret-change-in-production";

export const INTERNAL_API_TOKEN =
  process.env.INTERNAL_API_TOKEN ?? process.env.APP_SECRET_KEY ?? DEV_SECRET;

// Fail closed rather than run production on the committed defaults. A known
// AUTH_SECRET lets anyone forge a session JWT; a known internal token lets any
// caller reach FastAPI directly and choose its own X-Actor, which bypasses both
// the sign-in and the audit trail's attribution.
if (["production", "prod", "staging"].includes((process.env.APP_ENV ?? "development").toLowerCase())) {
  const insecure = [
    INTERNAL_API_TOKEN === DEV_SECRET && "INTERNAL_API_TOKEN (or APP_SECRET_KEY)",
    (process.env.AUTH_SECRET ?? DEV_AUTH_SECRET) === DEV_AUTH_SECRET && "AUTH_SECRET",
  ].filter(Boolean);
  if (insecure.length) {
    throw new Error(
      `APP_ENV=${process.env.APP_ENV} but these still hold their local-development ` +
        `defaults: ${insecure.join(", ")}. Set them to real secrets before starting.`,
    );
  }
}

export function internalApiHeaders(actor?: string | null): HeadersInit {
  const headers: Record<string, string> = {
    "X-Internal-Token": INTERNAL_API_TOKEN,
  };
  if (actor) {
    headers["X-Actor"] = actor;
  }
  return headers;
}
