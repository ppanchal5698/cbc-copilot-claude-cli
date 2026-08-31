"use client";

import { useState } from "react";
import Link from "next/link";
import { CaretDown, CaretRight } from "@phosphor-icons/react/dist/ssr";

import { formatMoneyShort } from "@/lib/format";
import type { Project } from "@/lib/types";

const STAGE_LABEL: Record<string, string> = {
  intake: "Intake",
  extraction: "Extraction",
  quote: "Quote",
  proposal: "Proposal",
};

function initials(brand: string): string {
  return brand
    .split(/\s+/)
    .map((word) => word[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function statusOf(project: Project): { label: string; colour: string; soft: string } {
  if (project.activeJob)
    return { label: "Claude is reading", colour: "var(--app-warn)", soft: "var(--app-warn-soft)" };
  if (project.counts.needsLook > 0)
    return {
      label: `${project.counts.needsLook} to check`,
      colour: "var(--app-neg)",
      soft: "var(--app-neg-soft)",
    };
  if (project.counts.total > 0)
    return { label: "All clear", colour: "var(--app-pos)", soft: "var(--app-pos-soft)" };
  return { label: "No lines yet", colour: "var(--app-tx-3)", soft: "transparent" };
}

/**
 * The board, grouped by brand.
 *
 * Grouping happens here rather than in the API: a national-accounts desk runs
 * tens of live bids, not thousands, and a client-side group avoids a second
 * shape for the same data.
 */
export function BoardGroups({ projects }: { projects: Project[] }) {
  const groups = new Map<string, Project[]>();
  for (const project of projects) {
    const brand = project.brand?.trim() || "Unbranded";
    groups.set(brand, [...(groups.get(brand) ?? []), project]);
  }

  const [closed, setClosed] = useState<Set<string>>(new Set());

  if (projects.length === 0) {
    return (
      <div
        className="grid place-items-center gap-2 rounded-xl px-6 py-16 text-center"
        style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
      >
        <span className="text-[14px] font-semibold">No bids here</span>
        <span className="max-w-[420px] text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
          Create a bid, drop the plan set in, and the schedules are read for you.
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {[...groups.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([brand, rows]) => {
          const open = !closed.has(brand);
          const value = rows.reduce((sum, row) => sum + (row.quoteTotal ?? 0), 0);
          const flags = rows.reduce((sum, row) => sum + row.counts.needsLook, 0);

          return (
            <div
              key={brand}
              className="overflow-hidden rounded-xl"
              style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
            >
              <button
                onClick={() =>
                  setClosed((current) => {
                    const next = new Set(current);
                    if (next.has(brand)) next.delete(brand);
                    else next.add(brand);
                    return next;
                  })
                }
                className="flex w-full items-center gap-3 px-4 py-3 text-left"
              >
                {open ? (
                  <CaretDown size={13} weight="bold" style={{ color: "var(--app-tx-3)" }} />
                ) : (
                  <CaretRight size={13} weight="bold" style={{ color: "var(--app-tx-3)" }} />
                )}
                <span
                  className="grid h-7 w-7 place-items-center rounded-md text-[11px] font-bold"
                  style={{ background: "var(--app-accent-soft)", color: "var(--app-accent)" }}
                >
                  {initials(brand)}
                </span>
                <span className="flex flex-col leading-tight">
                  <span className="text-[13.5px] font-semibold">{brand}</span>
                  <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                    {rows.length} in this programme
                  </span>
                </span>

                <span className="flex-1" />

                {flags > 0 && (
                  <span
                    className="rounded-full px-2 py-0.5 text-[11px]"
                    style={{ background: "var(--app-neg-soft)", color: "var(--app-neg)" }}
                  >
                    {flags} flagged
                  </span>
                )}
                <span className="flex flex-col items-end leading-tight">
                  <span
                    className="text-[10px] uppercase tracking-[0.07em]"
                    style={{ color: "var(--app-tx-3)" }}
                  >
                    Programme value
                  </span>
                  <span className="tnum text-[13.5px] font-semibold">
                    {value ? formatMoneyShort(value) : "—"}
                  </span>
                </span>
              </button>

              {open && (
                <div className="overflow-x-auto">
                  <div
                    className="grid min-w-[720px] gap-3 border-y px-4 py-2 text-[10.5px] uppercase tracking-[0.07em]"
                    style={{
                      gridTemplateColumns: "170px 1fr 110px 100px 90px 70px 110px",
                      borderColor: "var(--app-line)",
                      color: "var(--app-tx-3)",
                    }}
                  >
                    <span>Bid</span>
                    <span>Customer</span>
                    <span>Due</span>
                    <span className="text-right">Value</span>
                    <span>Stage</span>
                    <span className="text-right">Ver.</span>
                    <span>Status</span>
                  </div>

                  {rows.map((project) => {
                    const status = statusOf(project);
                    return (
                      <Link
                        key={project.id}
                        href={`/bids/${project.code}/${project.stage}`}
                        className="grid min-w-[720px] items-center gap-3 border-b px-4 py-2.5 no-underline last:border-b-0 hover:bg-[var(--app-panel-2)]"
                        style={{
                          gridTemplateColumns: "170px 1fr 110px 100px 90px 70px 110px",
                          borderColor: "var(--app-line)",
                        }}
                      >
                        <span className="flex min-w-0 flex-col leading-tight">
                          <span
                            className="tnum truncate text-[12.5px] font-semibold"
                            style={{ color: "var(--app-accent)" }}
                          >
                            {project.code}
                          </span>
                          <span
                            className="truncate text-[10.5px]"
                            style={{ color: "var(--app-tx-3)" }}
                          >
                            {project.name}
                          </span>
                        </span>
                        <span className="truncate text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
                          {project.gc ?? "—"}
                        </span>
                        <span className="text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                          {project.bidDue ? new Date(project.bidDue).toLocaleDateString() : "—"}
                        </span>
                        <span className="tnum text-right text-[12.5px] font-semibold">
                          {project.quoteTotal ? formatMoneyShort(project.quoteTotal) : "—"}
                        </span>
                        <span className="text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                          {STAGE_LABEL[project.stage]}
                        </span>
                        <span className="tnum text-right text-[12px]" style={{ color: "var(--app-tx-3)" }}>
                          v{project.version ?? 1}
                        </span>
                        <span>
                          <span
                            className="rounded-full px-2 py-0.5 text-[11px]"
                            style={{ background: status.soft, color: status.colour }}
                          >
                            {status.label}
                          </span>
                        </span>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
    </div>
  );
}
