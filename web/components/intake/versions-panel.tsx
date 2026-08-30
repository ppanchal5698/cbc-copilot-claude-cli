"use client";

import { useState } from "react";
import useSWR from "swr";
import { Checks, ClockCounterClockwise, Warning } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { proxyFetcher } from "@/lib/proxy-fetcher";

interface VersionSummary {
  id: string;
  version: number;
  reason: string;
  createdAt: string;
  createdBy: string;
  reconciled: boolean;
  lineItemCount: number;
  quoteLineCount: number;
}

interface VersionDiff {
  version: number;
  added: string[];
  removed: string[];
  changed: { mark: string; fields: string[]; before: Record<string, unknown>; after: Record<string, unknown> }[];
  pending: string;
}

/**
 * Addendum snapshots and diffs — interim UI for FR-14 until Matrix 4.1 rules land.
 */
export function VersionsPanel({ code }: { code: string }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [busy, setBusy] = useState(false);

  const { data, mutate } = useSWR<{
    versions: VersionSummary[];
    current: number;
    unreconciled: number;
    pending: string;
  }>(`/api/proxy/projects/${code}/versions`, proxyFetcher);

  const versions = data?.versions ?? [];
  if (versions.length === 0) return null;

  async function loadDiff(version: number) {
    if (expanded === version) {
      setExpanded(null);
      setDiff(null);
      return;
    }
    setExpanded(version);
    setDiff(null);
    const response = await fetch(`/api/proxy/projects/${code}/versions/${version}/diff`);
    if (!response.ok) {
      toast.error("Could not load the diff");
      return;
    }
    setDiff(await response.json());
  }

  async function reconcile(version: number) {
    setBusy(true);
    const response = await fetch(`/api/proxy/projects/${code}/versions/${version}/reconcile`, {
      method: "POST",
    });
    setBusy(false);
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      toast.error("Could not mark reconciled", { description: String(body.detail) });
      return;
    }
    toast.success(`Version ${version} marked reconciled`);
    mutate();
  }

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div
        className="flex items-center gap-2 border-b px-4 py-3.5"
        style={{ borderColor: "var(--app-line)" }}
      >
        <ClockCounterClockwise size={16} weight="duotone" style={{ color: "var(--app-accent)" }} />
        <span className="text-[15px] font-semibold">Addendum versions</span>
        {data?.unreconciled ? (
          <span
            className="rounded-full px-2 py-0.5 text-[10.5px] font-semibold"
            style={{ background: "var(--app-warn-soft)", color: "var(--app-warn)" }}
          >
            {data.unreconciled} unreconciled
          </span>
        ) : null}
      </div>

      <div className="divide-y" style={{ borderColor: "var(--app-line)" }}>
        {versions.map((entry) => (
          <div key={entry.id} className="px-4 py-3">
            <div className="flex items-start gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-semibold">v{entry.version}</span>
                  <span className="text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                    {entry.reason}
                  </span>
                  {entry.reconciled ? (
                    <span className="text-[10.5px]" style={{ color: "var(--app-pos)" }}>
                      reconciled
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
                  {entry.lineItemCount} line items · {entry.quoteLineCount} quote lines · by{" "}
                  {entry.createdBy}
                </p>
              </div>
              <button
                onClick={() => loadDiff(entry.version)}
                className="rounded-md px-2.5 py-1 text-[11.5px]"
                style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
              >
                {expanded === entry.version ? "Hide diff" : "View diff"}
              </button>
              {!entry.reconciled && (
                <button
                  onClick={() => reconcile(entry.version)}
                  disabled={busy}
                  className="flex items-center gap-1 rounded-md px-2.5 py-1 text-[11.5px] font-semibold disabled:opacity-50"
                  style={{ background: "var(--app-accent)", color: "#fff" }}
                >
                  <Checks size={12} weight="bold" />
                  Reconcile
                </button>
              )}
            </div>

            {expanded === entry.version && diff && (
              <div
                className="mt-3 rounded-lg p-3 text-[12px]"
                style={{ background: "var(--app-panel-2)", border: "1px solid var(--app-line)" }}
              >
                {diff.added.length > 0 && (
                  <p>
                    <strong>Added:</strong> {diff.added.join(", ") || "—"}
                  </p>
                )}
                {diff.removed.length > 0 && (
                  <p className="mt-1">
                    <strong>Removed:</strong> {diff.removed.join(", ") || "—"}
                  </p>
                )}
                {diff.changed.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {diff.changed.map((row) => (
                      <li key={row.mark}>
                        <strong>{row.mark}</strong> — {row.fields.join(", ")} changed
                      </li>
                    ))}
                  </ul>
                )}
                {diff.added.length === 0 && diff.removed.length === 0 && diff.changed.length === 0 && (
                  <p style={{ color: "var(--app-tx-3)" }}>No line-item changes detected against this snapshot.</p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <p
        className="flex items-center gap-1.5 border-t px-4 py-2.5 text-[10.5px]"
        style={{ borderColor: "var(--app-line)", color: "var(--app-warn)" }}
        title={data?.pending}
      >
        <Warning size={12} weight="duotone" />
        Reconciliation marks this version reviewed — merge rules are still pending (Matrix 4.1).
      </p>
    </section>
  );
}
