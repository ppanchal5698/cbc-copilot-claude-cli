"use client";

import Link from "next/link";

import { isAdminRole, translateJobError, type JobErrorAction } from "@/lib/job-error";
import type { Job } from "@/lib/types";

export function JobFailedBanner({
  job,
  role,
  stage,
  onAction,
}: {
  job: Job;
  role: string;
  stage: "extraction" | "quote" | "proposal" | "intake";
  onAction?: (action: JobErrorAction) => void;
}) {
  const translated = translateJobError(job.error, role, {
    errorCode: job.errorCode,
    stage,
  });
  if (!translated) return null;

  return (
    <div
      className="rounded-xl px-4 py-3 text-[12.5px]"
      style={{
        background: "var(--app-neg-soft)",
        border: "1px solid var(--app-neg-line)",
        color: "var(--app-neg)",
      }}
    >
      <p className="font-semibold">{translated.title}</p>
      <p className="mt-1 leading-relaxed" style={{ color: "var(--app-tx-2)" }}>
        {translated.message}
      </p>
      {translated.actions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {translated.actions.map((action) => {
            if (action.href?.startsWith("/") || action.href?.startsWith("#")) {
              if (action.href.startsWith("#")) {
                return (
                  <button
                    key={action.label}
                    type="button"
                    onClick={() => onAction?.(action)}
                    className="rounded-md px-2.5 py-1 text-[11.5px] font-semibold"
                    style={{
                      background: "var(--app-panel)",
                      border: "1px solid var(--app-neg-line)",
                      color: "var(--app-neg)",
                    }}
                  >
                    {action.label}
                  </button>
                );
              }
              return (
                <Link
                  key={action.label}
                  href={action.href}
                  className="rounded-md px-2.5 py-1 text-[11.5px] font-semibold no-underline"
                  style={{
                    background: "var(--app-panel)",
                    border: "1px solid var(--app-neg-line)",
                    color: "var(--app-neg)",
                  }}
                >
                  {action.label}
                </Link>
              );
            }
            return (
              <button
                key={action.label}
                type="button"
                onClick={() => onAction?.(action)}
                className="rounded-md px-2.5 py-1 text-[11.5px] font-semibold"
                style={{
                  background: "var(--app-panel)",
                  border: "1px solid var(--app-neg-line)",
                  color: "var(--app-neg)",
                }}
              >
                {action.label}
              </button>
            );
          })}
        </div>
      )}
      {isAdminRole(role) && translated.technical && (
        <details className="mt-3">
          <summary
            className="cursor-pointer text-[11px] font-medium"
            style={{ color: "var(--app-tx-3)" }}
          >
            Technical details
          </summary>
          <pre
            className="mt-1.5 overflow-x-auto whitespace-pre-wrap rounded-md p-2 text-[10.5px] font-mono"
            style={{
              background: "var(--app-panel)",
              border: "1px solid var(--app-line)",
              color: "var(--app-tx-2)",
            }}
          >
            {translated.technical}
          </pre>
        </details>
      )}
    </div>
  );
}
