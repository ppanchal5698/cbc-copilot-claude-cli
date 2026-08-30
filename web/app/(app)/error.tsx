"use client";

import { useEffect } from "react";
import { ArrowClockwise, WarningOctagon } from "@phosphor-icons/react/dist/ssr";

/**
 * The boundary for the whole signed-in shell.
 *
 * The bid pages re-throw anything that is not a 404, and before this existed
 * that meant Next's default error screen: no wording from the API, no way back,
 * and no retry. `retry` re-runs the failed segment on the server, which is what
 * an estimator wants when the API was simply restarting.
 *
 * Next 16 passes `retry`, not `reset` - see
 * node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/error.md
 */
export default function AppError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error("Ops-Hub page error:", error);
  }, [error]);

  return (
    <main className="grid flex-1 place-items-center p-6">
      <div className="grid max-w-[520px] justify-items-center gap-3 text-center">
        <span
          className="grid h-11 w-11 place-items-center rounded-xl"
          style={{ background: "var(--app-neg-soft)", color: "var(--app-neg)" }}
        >
          <WarningOctagon size={22} weight="duotone" />
        </span>

        <h1 className="text-[17px] font-semibold">This screen could not be loaded</h1>

        <p className="text-[12.5px] leading-relaxed" style={{ color: "var(--app-tx-2)" }}>
          {/* The API's own message, which is usually the actionable part - it
              names the host when the service is simply not running. */}
          {error.message || "Something went wrong while reading this bid."}
        </p>

        <div className="mt-1 flex flex-wrap justify-center gap-2">
          <button
            onClick={retry}
            className="flex items-center gap-1.5 rounded-md px-3.5 py-2 text-[12.5px] font-semibold"
            style={{ background: "var(--app-accent)", color: "#fff" }}
          >
            <ArrowClockwise size={14} weight="bold" />
            Try again
          </button>
          <a
            href="/dashboard"
            className="rounded-md px-3.5 py-2 text-[12.5px] no-underline"
            style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
          >
            Back to the dashboard
          </a>
        </div>

        {error.digest && (
          <p className="mt-1 text-[10.5px]" style={{ color: "var(--app-tx-3)" }}>
            Reference {error.digest} — quote this if you report it.
          </p>
        )}

        <p className="mt-2 text-[11px]" style={{ color: "var(--app-tx-3)" }}>
          Nothing was sent and nothing was lost. Work already saved against this bid is untouched.
        </p>
      </div>
    </main>
  );
}
