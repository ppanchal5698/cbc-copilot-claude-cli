"use client";

import { errorMessage } from "@/lib/proxy-fetcher";

/** Inline retry banner for SWR fetch failures. */
export function FetchError({
  title,
  error,
  onRetry,
  compact = false,
}: {
  title: string;
  error: unknown;
  onRetry: () => void;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <p className="px-4 py-3 text-[12px]" style={{ color: "var(--app-neg)" }}>
        {title}: {errorMessage(error)}{" "}
        <button
          type="button"
          onClick={onRetry}
          className="underline"
          style={{ color: "var(--app-tx-2)" }}
        >
          Retry
        </button>
      </p>
    );
  }

  return (
    <div className="grid place-items-center gap-2 px-6 py-8 text-center">
      <span className="text-[13.5px] font-semibold" style={{ color: "var(--app-neg)" }}>
        {title}
      </span>
      <span className="max-w-[420px] text-[12px]" style={{ color: "var(--app-tx-2)" }}>
        {errorMessage(error)}
      </span>
      <button
        type="button"
        onClick={onRetry}
        className="mt-1 rounded-md px-3 py-1.5 text-[12px]"
        style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
      >
        Try again
      </button>
    </div>
  );
}
