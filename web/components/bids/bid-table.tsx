import Link from "next/link";

import { formatMoneyShort } from "@/lib/format";
import type { Project } from "@/lib/types";

const STAGE_LABEL: Record<string, string> = {
  intake: "Intake",
  extraction: "Extraction",
  quote: "Quote",
  proposal: "Proposal",
};

function StatusPill({ project }: { project: Project }) {
  if (project.activeJob) {
    return (
      <span
        className="anim-fadein rounded-full px-2 py-0.5 text-[11px]"
        style={{ background: "var(--app-warn-soft)", color: "var(--app-warn)" }}
      >
        Claude is reading…
      </span>
    );
  }
  if (project.counts.needsLook > 0) {
    return (
      <span
        className="rounded-full px-2 py-0.5 text-[11px]"
        style={{ background: "var(--app-neg-soft)", color: "var(--app-neg)" }}
      >
        {project.counts.needsLook} to check
      </span>
    );
  }
  if (project.counts.total > 0) {
    return (
      <span
        className="rounded-full px-2 py-0.5 text-[11px]"
        style={{ background: "var(--app-pos-soft)", color: "var(--app-pos)" }}
      >
        All clear
      </span>
    );
  }
  return (
    <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
      No lines yet
    </span>
  );
}

export function BidTable({ projects }: { projects: Project[] }) {
  if (projects.length === 0) {
    return (
      <div
        className="grid place-items-center gap-2 rounded-xl px-6 py-16 text-center"
        style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
      >
        <span className="text-[14px] font-semibold">No bids yet</span>
        <span className="max-w-[420px] text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
          Create a bid, drop the plan set in, and the schedules and elevations are read for you.
        </span>
      </div>
    );
  }

  return (
    <div
      className="overflow-hidden rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div
        className="grid items-center gap-3 border-b px-4 py-2.5 text-[10.5px] uppercase tracking-[0.07em]"
        style={{
          gridTemplateColumns: "110px 1fr 150px 110px 120px 110px",
          borderColor: "var(--app-line)",
          color: "var(--app-tx-3)",
        }}
      >
        <span>Number</span>
        <span>Job</span>
        <span>Customer</span>
        <span>Stage</span>
        <span>Status</span>
        <span className="text-right">Quote</span>
      </div>

      {projects.map((project) => (
        <Link
          key={project.id}
          href={`/bids/${project.code}/${project.stage}`}
          className="grid items-center gap-3 border-b px-4 py-3 no-underline transition last:border-b-0 hover:bg-[var(--app-panel-2)]"
          style={{ gridTemplateColumns: "110px 1fr 150px 110px 120px 110px", borderColor: "var(--app-line)" }}
        >
          <span className="tnum text-[12.5px] font-semibold" style={{ color: "var(--app-accent)" }}>
            {project.code}
          </span>
          <span className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-[13px]" style={{ color: "var(--app-tx)" }}>
              {project.name}
            </span>
            <span className="truncate text-[11px]" style={{ color: "var(--app-tx-3)" }}>
              {project.location ?? "location not recorded"}
              {project.documentCount > 0 && ` · ${project.documentCount} document${project.documentCount === 1 ? "" : "s"}`}
            </span>
          </span>
          <span className="truncate text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
            {project.gc ?? "—"}
          </span>
          <span className="text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
            {STAGE_LABEL[project.stage]}
          </span>
          <span>
            <StatusPill project={project} />
          </span>
          <span className="tnum text-right text-[12.5px] font-semibold">
            {project.quoteTotal ? formatMoneyShort(project.quoteTotal) : "—"}
          </span>
        </Link>
      ))}
    </div>
  );
}
