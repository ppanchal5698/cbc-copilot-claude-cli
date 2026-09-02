/**
 * Shared secret between the Next.js server and the FastAPI service.
 *
 * SERVER ONLY - the guard is not decoration. This module holds the fallback
 * internal token and the fallback AUTH_SECRET, and it was reaching the browser
 * bundle through lib/api.ts, which a client component imported for one URL
 * helper.
 */
import "server-only";

const DEV_SECRET = "cbc-local-dev-key-change-me";
const DEV_AUTH_SECRET = "cbc-opshub-local-dev-secret-change-in-production";

export const INTERNAL_API_TOKEN =
  process.env.INTERNAL_API_TOKEN ?? process.env.APP_SECRET_KEY ?? DEV_SECRET;

function isNextProductionBuild(): boolean {
  // APP_ENV=production is set in web/Dockerfile so dev-auth cannot bake seed
  // credentials at build time. The secret check must not run in that same
  // phase — AUTH_SECRET and INTERNAL_API_TOKEN are injected at container start,
  // not during `npm run build`.
  return (
    process.env.NEXT_PHASE === "phase-production-build" ||
    process.env.npm_lifecycle_event === "build"
  );
}

let productionSecretsChecked = false;

/** Fail closed at runtime, not when Next is compiling the production bundle. */
export function assertProductionSecrets(): void {
  if (productionSecretsChecked || isNextProductionBuild()) {
    return;
  }

  const appEnv = (process.env.APP_ENV ?? "development").toLowerCase();
  if (!["production", "prod", "staging"].includes(appEnv)) {
    productionSecretsChecked = true;
    return;
  }

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

  productionSecretsChecked = true;
}

export function internalApiHeaders(actor?: string | null): HeadersInit {
  assertProductionSecrets();

  const headers: Record<string, string> = {
    "X-Internal-Token": INTERNAL_API_TOKEN,
  };
  if (actor) {
    headers["X-Actor"] = actor;
  }
  return headers;
}
