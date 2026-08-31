import Link from "next/link";

import { PageHeader } from "@/components/shell/page-header";
import { BoardGroups } from "@/components/bids/board-groups";
import { BidBoardSearch } from "@/components/bids/bid-board-search";
import { NewBidDialog } from "@/components/bids/new-bid-dialog";
import { api } from "@/lib/api";
import type { Project, Stage } from "@/lib/types";

export const dynamic = "force-dynamic";

const FILTERS: { key: Stage | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "intake", label: "Intake" },
  { key: "extraction", label: "Extraction" },
  { key: "quote", label: "Quote" },
  { key: "proposal", label: "Proposal" },
];

export default async function BidBoardPage({
  searchParams,
}: {
  searchParams: Promise<{ stage?: string; q?: string }>;
}) {
  const { stage, q } = await searchParams;

  const query = new URLSearchParams();
  if (stage && stage !== "all") query.set("stage", stage);
  if (q) query.set("q", q);

  // See the dashboard: an unreachable API is reported by the error boundary,
  // not disguised as an empty board.
  const projects = (
    await api.get<{ projects: Project[] }>(`/api/projects?${query.toString()}`)
  ).projects;

  return (
    <>
      <PageHeader crumbs={[{ label: "Workspace" }, { label: "Bid board" }]} />

      <main id="main-content" className="min-h-0 flex-1 overflow-auto p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-[20px] font-semibold">Bid board</h1>
            <p className="mt-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
              {projects.length} bid{projects.length === 1 ? "" : "s"} · grouped by brand
              {stage && stage !== "all" ? ` in ${stage}` : ""}
            </p>
          </div>
          <NewBidDialog />
        </div>

        <div className="mb-4 flex gap-1.5">
          {FILTERS.map((filter) => {
            const active = (stage ?? "all") === filter.key;
            return (
              <Link
                key={filter.key}
                href={`/bids?stage=${filter.key}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
                aria-current={active ? "page" : undefined}
                className="rounded-md px-3 py-1.5 text-[12.5px] no-underline"
                style={{
                  background: active ? "var(--app-accent-soft)" : "var(--app-panel)",
                  border: `1px solid ${active ? "var(--app-accent-line)" : "var(--app-line)"}`,
                  color: active ? "var(--app-accent)" : "var(--app-tx-2)",
                }}
              >
                {filter.label}
              </Link>
            );
          })}
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-3">
          <BidBoardSearch key={q ?? ""} stage={stage} initialQuery={q ?? ""} />
        </div>

        {projects.length === 0 ? (
          <div
            className="grid place-items-center gap-2 rounded-xl px-6 py-16 text-center"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            <span className="text-[15px] font-semibold">
              {q ? "No bids match that search" : "No bids yet"}
            </span>
            <span className="max-w-[420px] text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
              {q
                ? "Try a different code, name, or brand — or clear the search to see all bids."
                : "Create a bid to start intake. Upload a plan set and Claude reads the openings for you."}
            </span>
            {!q && <NewBidDialog />}
          </div>
        ) : (
          <BoardGroups projects={projects} />
        )}
      </main>
    </>
  );
}
