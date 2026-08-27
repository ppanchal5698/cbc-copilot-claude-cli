"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import useSWR from "swr";
import { X } from "@phosphor-icons/react/dist/ssr";

import { useUiState } from "@/components/shell/ui-state";
import type { Job } from "@/lib/types";

// xterm builds against the DOM, so it must never be evaluated on the server.
const RunTerminal = dynamic(
  () => import("@/components/terminal/run-terminal").then((m) => m.RunTerminal),
  { ssr: false },
);

const fetcher = (url: string) => fetch(url).then((r) => r.json());

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

  const { data } = useSWR<{ jobs: Job[] }>(
    terminalOpen && code ? `/api/proxy/jobs?project=${encodeURIComponent(code)}&limit=12` : null,
    fetcher,
    { refreshInterval: 5000 },
  );

  if (!terminalOpen || !code) return null;

  const jobs = data?.jobs ?? [];
  const active = jobs.find((j) => j.id === selected) ?? jobs[0];

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-40 flex flex-col"
      style={{
        height: "min(52vh, 560px)",
        background: "var(--app-bg-2)",
        borderTop: "1px solid var(--app-line)",
        boxShadow: "var(--app-sh-3)",
      }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2"
        style={{ borderBottom: "1px solid var(--app-line)" }}
      >
        <span className="text-[12px] font-semibold">Run terminal</span>
        <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
          {code}
        </span>

        <div className="ml-2 flex flex-wrap gap-1">
          {jobs.slice(0, 8).map((job) => {
            const on = active?.id === job.id;
            return (
              <button
                key={job.id}
                onClick={() => setSelected(job.id)}
                className="rounded px-2 py-0.5 text-[11px]"
                style={{
                  background: on ? "var(--app-accent-soft)" : "transparent",
                  border: `1px solid ${on ? "var(--app-accent-line)" : "var(--app-line)"}`,
                  color: on ? "var(--app-accent)" : "var(--app-tx-3)",
                }}
                title={job.status}
              >
                {job.type}
                {job.status === "running" ? " ·" : ""}
              </button>
            );
          })}
        </div>

        <span className="flex-1" />
        <button
          onClick={() => setRaw((r) => !r)}
          className="rounded px-2 py-0.5 text-[11px]"
          style={{
            border: "1px solid var(--app-line)",
            color: raw ? "var(--app-accent)" : "var(--app-tx-3)",
          }}
          title="Show the CLI event stream exactly as it arrived"
        >
          raw
        </button>
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
