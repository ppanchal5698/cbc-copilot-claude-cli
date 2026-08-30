import type { Job } from "@/lib/types";

export type RunPill = { label: string; tone: "running" | "done" | "failed" } | null;

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
    // An autopilot run is one job that can last an hour. Naming the phase it has
    // reached is the difference between watching it work and watching a spinner.
    const label =
      job.type === "run_full_pipeline"
        ? phase
          ? `Autopilot · ${phase}…`
          : "Autopilot · starting…"
        : "Reading the bid set…";
    return { label, tone: "running" };
  }
  if (job.status === "queued") return { label: "Queued for Claude…", tone: "running" };
  if (job.status === "failed") return { label: "Run failed", tone: "failed" };
  return { label: `Pass complete · ${itemCount ?? 0} items`, tone: "done" };
}
