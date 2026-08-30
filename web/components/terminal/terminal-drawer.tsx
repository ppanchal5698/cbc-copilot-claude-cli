"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import useSWR from "swr";
import { X } from "@phosphor-icons/react/dist/ssr";

import { useUiState } from "@/components/shell/ui-state";
import { useDialog } from "@/hooks/use-dialog";
import type { Job, JobStatus } from "@/lib/types";
import { proxyFetcher } from "@/lib/proxy-fetcher";

// xterm builds against the DOM, so it must never be evaluated on the server.
const RunTerminal = dynamic(
  () => import("@/components/terminal/run-terminal").then((m) => m.RunTerminal),
  { ssr: false },
);

function statusColor(status: JobStatus): string {
  switch (status) {
    case "running":
      return "var(--app-accent)";
    case "done":
      return "var(--app-pos)";
    case "failed":
    case "cancelled":
      return "var(--app-neg)";
    default:
      return "var(--app-tx-3)";
  }
}

function statusLabel(status: JobStatus): string {
  switch (status) {
    case "running":
      return "running";
    case "done":
      return "done";
    case "failed":
      return "failed";
    case "cancelled":
      return "cancelled";
    default:
      return "queued";
  }
}

/**
 * The run terminal, docked at the bottom of whatever bid is on screen.
 *
 * It defaults to the newest job for that bid, which is almost always the one you
 * want, and lets you page back through earlier runs of the same bid — a failed
 * extraction is usually diagnosed by reading the run before it.
 */
export function TerminalDrawer({ code }: { code: string | null }) {
  const { terminalOpen, setTerminalOpen } = useUiState();
  const [selected, setSelected] = useState<string | null>(null);
  const [raw, setRaw] = useState(false);

  const close = useCallback(() => setTerminalOpen(false), [setTerminalOpen]);
  const dialogRef = useDialog<HTMLDivElement>(terminalOpen, close);

  const { data } = useSWR<{ jobs: Job[] }>(
    terminalOpen && code ? `/api/proxy/jobs?project=${encodeURIComponent(code)}&limit=12` : null,
    proxyFetcher,
    { refreshInterval: 5000 },
  );

  if (!terminalOpen || !code) return null;

  const jobs = data?.jobs ?? [];
  const active = jobs.find((j) => j.id === selected) ?? jobs[0];

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-label={`Run terminal for ${code}`}
      className="fixed inset-x-0 bottom-0 z-40 flex flex-col"
      style={{
        height: "min(52vh, 560px)",
        background: "var(--app-bg-2)",
        borderTop: "1px solid var(--app-line)",
        boxShadow: "var(--app-sh-3)",
      }}
    >
      <div
        className="flex flex-wrap items-center gap-2 px-3 py-2"
        style={{ borderBottom: "1px solid var(--app-line)" }}
      >
        <span className="text-[12px] font-semibold">Run terminal</span>
        <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
          {code}
        </span>

        <div className="ml-2 flex flex-wrap gap-1">
          {jobs.slice(0, 8).map((job) => {
            const on = active?.id === job.id;
            const color = statusColor(job.status);
            return (
              <button
                key={job.id}
                onClick={() => setSelected(job.id)}
                className="flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px]"
                style={{
                  background: on ? "var(--app-accent-soft)" : "transparent",
                  border: `1px solid ${on ? "var(--app-accent-line)" : "var(--app-line)"}`,
                  color: on ? "var(--app-accent)" : "var(--app-tx-3)",
                }}
                title={`${job.type} · ${job.status}`}
              >
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{
                    background: color,
                    boxShadow: job.status === "running" ? `0 0 6px ${color}` : undefined,
                  }}
                />
                <span>{job.type}</span>
                {on ? (
                  <span className="text-[10px] opacity-80">{statusLabel(job.status)}</span>
                ) : null}
              </button>
            );
          })}
        </div>

        <span className="flex-1" />
        <div
          className="flex overflow-hidden rounded"
          style={{ border: "1px solid var(--app-line)" }}
        >
          <button
            onClick={() => setRaw(false)}
            aria-pressed={!raw}
            className="px-2 py-0.5 text-[11px]"
            style={{
              background: !raw ? "var(--app-accent-soft)" : "transparent",
              color: !raw ? "var(--app-accent)" : "var(--app-tx-3)",
            }}
          >
            Structured
          </button>
          <button
            onClick={() => setRaw(true)}
            aria-pressed={raw}
            className="px-2 py-0.5 text-[11px]"
            style={{
              background: raw ? "var(--app-accent-soft)" : "transparent",
              color: raw ? "var(--app-accent)" : "var(--app-tx-3)",
              borderLeft: "1px solid var(--app-line)",
            }}
          >
            Raw
          </button>
        </div>
        <button
          onClick={() => setTerminalOpen(false)}
          aria-label="Close the run terminal"
          className="rounded p-1"
          style={{ color: "var(--app-tx-3)" }}
        >
          <X size={14} weight="bold" />
        </button>
      </div>

      <div className="min-h-0 flex-1">
        {active ? (
          <RunTerminal
            key={`${active.id}-${raw}`}
            jobId={active.id}
            status={active.status}
            raw={raw}
          />
        ) : (
          <div className="px-3 py-4 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
            No runs yet for this bid.
          </div>
        )}
      </div>
    </div>
  );
}
