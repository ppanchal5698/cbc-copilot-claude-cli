"use client";

import Link from "next/link";
import { CheckSquare, ListChecks, Table, FileText } from "@phosphor-icons/react/dist/ssr";

import { formatMoneyShort } from "@/lib/format";
import type { Project, Stage } from "@/lib/types";

const STAGES: { key: Stage; label: string; Icon: typeof CheckSquare }[] = [
  { key: "intake", label: "Intake", Icon: CheckSquare },
  { key: "extraction", label: "Extraction & entry", Icon: ListChecks },
  { key: "quote", label: "Quote", Icon: Table },
  { key: "proposal", label: "Proposal", Icon: FileText },
];

const ORDER: Stage[] = ["intake", "extraction", "quote", "proposal"];

export function StageBar({ project, current }: { project: Project; current: Stage }) {
  const currentIndex = ORDER.indexOf(current);

  function subtitle(stage: Stage): string {
    switch (stage) {
      case "intake":
        return `${project.documentCount} document${project.documentCount === 1 ? "" : "s"}`;
      case "extraction":
        return project.counts.total
          ? `${project.counts.needsLook} to check`
          : "not read yet";
      case "quote":
        return project.quoteTotal ? formatMoneyShort(project.quoteTotal) : "not priced";
      case "proposal":
        return project.stage === "proposal" ? "Draft" : "—";
    }
  }

  return (
    <div
      className="flex shrink-0 items-center gap-4 border-b px-5 py-3"
      style={{ borderColor: "var(--app-line)", background: "var(--app-bg)" }}
    >
      <span className="flex w-[230px] shrink-0 flex-col leading-tight">
        <span className="truncate text-[13.5px] font-semibold" title={project.name}>
          {project.name}
        </span>
        <span className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
          {project.code}
          {project.projectNumber ? ` / ${project.projectNumber}` : ""}
          {project.bidDue ? ` · bid due ${new Date(project.bidDue).toLocaleDateString()}` : ""}
        </span>
      </span>

      <span className="flex flex-1 items-center gap-2.5">
        {STAGES.map(({ key, label, Icon }, index) => {
          const active = key === current;
          const done = index < currentIndex;
          return (
            <Link
              key={key}
              href={`/bids/${project.code}/${key}`}
              className="flex flex-1 items-center gap-2.5 rounded-lg px-3.5 py-2.5 no-underline transition"
              style={{
                background: active ? "var(--app-accent-soft)" : "var(--app-panel)",
                border: `1px solid ${active ? "var(--app-accent-line)" : "var(--app-line)"}`,
              }}
            >
              <span
                className="grid h-[26px] w-[26px] shrink-0 place-items-center rounded-md"
                style={{
                  background: done
                    ? "var(--app-pos-soft)"
                    : active
                      ? "var(--app-accent)"
                      : "var(--app-panel-2)",
                  color: done ? "var(--app-pos)" : active ? "#fff" : "var(--app-tx-3)",
                }}
              >
                <Icon size={14} weight="duotone" />
              </span>
              <span className="flex min-w-0 flex-col leading-tight">
                <span
                  className="truncate text-[12.5px] font-semibold"
                  style={{ color: active ? "var(--app-accent)" : "var(--app-tx)" }}
                >
                  {label}
                </span>
                <span className="truncate text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                  {subtitle(key)}
                </span>
              </span>
            </Link>
          );
        })}
      </span>

      <span className="flex w-[150px] shrink-0 flex-col items-end gap-1">
        <span className="text-[10.5px] uppercase tracking-[0.08em]" style={{ color: "var(--app-tx-3)" }}>
          Bid progress
        </span>
        <span className="flex w-full items-center gap-2">
          <span
            className="h-1 flex-1 overflow-hidden rounded-full"
            style={{ background: "var(--app-panel-2)" }}
          >
            <span
              className="block h-full rounded-full transition-all"
              style={{ width: `${project.progress}%`, background: "var(--app-accent)" }}
            />
          </span>
          <span className="tnum text-[12px] font-semibold">{project.progress}%</span>
        </span>
      </span>
    </div>
  );
}
