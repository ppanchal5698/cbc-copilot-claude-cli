"use client";

import useSWR from "swr";

import { FetchError } from "@/components/ui/fetch-error";
import { endpoints } from "@/lib/endpoints";
import { proxyFetcher } from "@/lib/proxy-fetcher";
import type { JobMetrics } from "@/lib/types";

/** How long ago, in words. The exact timestamp is not the point; "20m" is. */
function ago(iso: string | null): string {
  if (!iso) return "—";
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 90) return `${Math.round(seconds)}s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

function seconds(value: number | null): string {
  if (value === null) return "—";
  return value < 90 ? `${value.toFixed(0)}s` : `${(value / 60).toFixed(1)}m`;
}

/**
 * The queue, without reading `docker logs`.
 *
 * Until this existed the only operational view of the worker was its log stream,
 * which cannot answer "is it backed up" or "which job type is failing" without a
 * person scrolling. The numbers were always in MongoDB.
 */
export function QueueMetricsPanel() {
  const { data, error, isLoading, mutate } = useSWR<JobMetrics>(
    endpoints.jobMetrics(24),
    proxyFetcher,
    { refreshInterval: 15_000, keepPreviousData: true },
  );

  const types = Object.entries(data?.byType ?? {}).sort(
    (a, b) => b[1].total - a[1].total,
  );

  // Any failure at all is worth colouring. A queue that is merely busy is not.
  const failing = (data?.failed ?? 0) > 0;

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <h2 className="text-[15px] font-semibold">Job queue</h2>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Depth now, and throughput over the last {data?.windowHours ?? 24} hours.
        </p>
      </div>

      <div className="px-4 py-3.5">
        {error && (
          <FetchError title="Could not read the queue" error={error} onRetry={() => mutate()} />
        )}
        {isLoading && !data && (
          <p className="text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
            Reading the queue…
          </p>
        )}

        {data && (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Queued", String(data.queued), undefined],
                ["Running", String(data.running), undefined],
                ["Oldest wait", ago(data.oldestQueuedAt), undefined],
                [
                  "Failure rate",
                  // null, not 0%: no news is not good news.
                  data.failureRate === null
                    ? "—"
                    : `${(data.failureRate * 100).toFixed(0)}%`,
                  failing ? "var(--app-neg)" : undefined,
                ],
              ].map(([label, value, colour]) => (
                <div key={label as string}>
                  <p className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                    {label}
                  </p>
                  <p
                    className="tnum text-[19px] font-semibold"
                    style={colour ? { color: colour as string } : undefined}
                  >
                    {value}
                  </p>
                </div>
              ))}
            </div>

            {types.length > 0 && (
              <table className="mt-4 w-full text-[12.5px]">
                <thead>
                  <tr style={{ color: "var(--app-tx-3)" }}>
                    <th className="pb-1 text-left font-normal">Job type</th>
                    <th className="pb-1 text-right font-normal">Done</th>
                    <th className="pb-1 text-right font-normal">Failed</th>
                    <th className="pb-1 text-right font-normal">Average</th>
                  </tr>
                </thead>
                <tbody>
                  {types.map(([type, row]) => (
                    <tr key={type} style={{ borderTop: "1px solid var(--app-line)" }}>
                      <td className="py-1.5">{type.replace(/_/g, " ")}</td>
                      <td className="tnum py-1.5 text-right">{row.done}</td>
                      <td
                        className="tnum py-1.5 text-right"
                        style={row.failed > 0 ? { color: "var(--app-neg)" } : undefined}
                      >
                        {row.failed}
                      </td>
                      <td className="tnum py-1.5 text-right">{seconds(row.avgSeconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {types.length === 0 && (
              <p className="mt-3 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
                No jobs in the window. Nothing is wrong; nothing has run.
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
