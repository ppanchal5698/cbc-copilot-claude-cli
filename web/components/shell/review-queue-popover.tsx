"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Bell, CaretRight } from "@phosphor-icons/react/dist/ssr";

import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useUiState } from "@/components/shell/ui-state";
import { proxyFetcher } from "@/lib/proxy-fetcher";
import type { Project } from "@/lib/types";

export function ReviewQueuePopover({
  reviewCount,
  code,
}: {
  reviewCount?: number;
  code?: string | null;
}) {
  const { focusMode } = useUiState();
  const [open, setOpen] = useState(false);

  const { data } = useSWR<{ projects: Project[] }>(
    open ? "/api/proxy/projects" : null,
    proxyFetcher,
  );

  const flagged =
    data?.projects
      ?.filter((project) => project.counts.needsLook > 0)
      .sort((a, b) => {
        if (code && a.code === code) return -1;
        if (code && b.code === code) return 1;
        return b.counts.needsLook - a.counts.needsLook;
      }) ?? [];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-label={
          reviewCount
            ? `Review queue — ${reviewCount} line${reviewCount === 1 ? "" : "s"} need a look`
            : "Review queue — nothing flagged"
        }
        title="Review queue"
        className="relative grid h-8 w-8 place-items-center rounded-md border-0 bg-transparent p-0"
        style={{ color: "var(--app-tx-2)" }}
      >
        <Bell size={16} weight="duotone" />
        {!!reviewCount && !focusMode && (
          <span
            className="tnum absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] font-semibold"
            style={{ background: "var(--app-neg)", color: "#fff" }}
          >
            {reviewCount}
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-80 p-0"
        style={{
          background: "var(--app-panel)",
          border: "1px solid var(--app-line)",
          color: "var(--app-tx)",
        }}
      >
        <PopoverHeader className="border-b px-3 py-2.5" style={{ borderColor: "var(--app-line)" }}>
          <PopoverTitle className="text-[13px] font-semibold">Review queue</PopoverTitle>
          <p className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
            Lines flagged for your review across open bids
          </p>
        </PopoverHeader>

        <div className="max-h-64 overflow-auto py-1">
          {flagged.length === 0 ? (
            <p className="px-3 py-4 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
              Nothing flagged for review
            </p>
          ) : (
            flagged.map((project) => (
              <Link
                key={project.id}
                href={`/bids/${project.code}/extraction`}
                onClick={() => setOpen(false)}
                className="flex items-center gap-2 px-3 py-2.5 no-underline transition hover:bg-[var(--app-panel-2)]"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px] font-medium" style={{ color: "var(--app-tx)" }}>
                    {project.jobName ?? project.name}
                  </span>
                  <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                    {project.code}
                  </span>
                </span>
                <span
                  className="tnum shrink-0 rounded-full px-2 py-0.5 text-[10.5px] font-semibold"
                  style={{ background: "var(--app-neg-soft)", color: "var(--app-neg)" }}
                >
                  {project.counts.needsLook}
                </span>
                <CaretRight size={12} style={{ color: "var(--app-tx-3)" }} />
              </Link>
            ))
          )}
        </div>

        <div className="border-t px-3 py-2" style={{ borderColor: "var(--app-line)" }}>
          <Link
            href="/bids?stage=extraction"
            onClick={() => setOpen(false)}
            className="text-[11.5px] font-medium no-underline"
            style={{ color: "var(--app-accent)" }}
          >
            View all bids
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
