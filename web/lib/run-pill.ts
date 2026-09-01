import type { Job } from "@/lib/types";
import { jobTypeLabel } from "@/lib/job-error";

export type RunPill = { label: string; tone: "running" | "done" | "failed" } | null;

function runningLabel(job: Job, phase?: string | null): string {
  if (job.type === "run_full_pipeline") {
    return phase ? `Autopilot · ${phase}…` : "Autopilot · starting…";
  }
  const byType: Record<string, string> = {
    extract_bid_set: "Reading the bid set…",
    rerun_extraction: "Re-reading the bid set…",
    match_and_price: "Pricing lines…",
    build_proposal: "Building proposal…",
    ingest_addendum: "Reading addendum…",
  };
  return byType[job.type] ?? `${jobTypeLabel(job.type)}…`;
}

/**
 * The status pill in the header.
 *
 * Lives outside the client component so server pages can call it - a plain
 * function exported from a "use client" module is not callable on the server.
 */
export function runPillFor(
  job: Job | null | undefined,
  itemCount?: number,
  phase?: string | null,
): RunPill {
  if (!job) {
    return itemCount ? { label: `Pass complete · ${itemCount} items`, tone: "done" } : null;
  }
  if (job.status === "running") {
    return { label: runningLabel(job, phase), tone: "running" };
  }
  if (job.status === "queued") return { label: "Queued…", tone: "running" };
  if (job.status === "failed") return { label: "Needs attention", tone: "failed" };
  return { label: `Pass complete · ${itemCount ?? 0} items`, tone: "done" };
}
