import { PageHeader } from "@/components/shell/page-header";
import { BoardGroups } from "@/components/bids/board-groups";
import { NewBidDialog } from "@/components/bids/new-bid-dialog";
import { ApiError, api } from "@/lib/api";
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

  let projects: Project[] = [];
  let apiError: string | null = null;
  try {
    projects = (
      await api.get<{ projects: Project[] }>(`/api/projects?${query.toString()}`)
    ).projects;
  } catch (error) {
    apiError = error instanceof ApiError ? error.message : String(error);
  }

  return (
    <>
      <PageHeader crumbs={[{ label: "Workspace" }, { label: "Bid board" }]} />

      <main className="min-h-0 flex-1 overflow-auto p-6">
        <div className="mb-5 flex items-end justify-between">
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
              <a
                key={filter.key}
                href={`/bids?stage=${filter.key}`}
                className="rounded-md px-3 py-1.5 text-[12.5px] no-underline"
                style={{
                  background: active ? "var(--app-accent-soft)" : "var(--app-panel)",
                  border: `1px solid ${active ? "var(--app-accent-line)" : "var(--app-line)"}`,
                  color: active ? "var(--app-accent)" : "var(--app-tx-2)",
                }}
              >
                {filter.label}
              </a>
            );
          })}
        </div>

        {apiError && (
          <div
            className="mb-5 rounded-lg px-4 py-3 text-[12.5px]"
            style={{
              background: "var(--app-neg-soft)",
              border: "1px solid var(--app-neg-line)",
              color: "var(--app-neg)",
            }}
          >
            {apiError}
          </div>
        )}

        <BoardGroups projects={projects} />
      </main>
    </>
  );
}
