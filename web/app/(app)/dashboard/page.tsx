import Link from "next/link";
import {
  ListChecks,
  CaretRight,
  Buildings,
  Timer,
  WarningCircle,
  Lightning,
  FileText,
  Table,
  Tray,
} from "@phosphor-icons/react/dist/ssr";

import { auth } from "@/auth";
import { PageHeader } from "@/components/shell/page-header";
import { NewBidDialog } from "@/components/bids/new-bid-dialog";
import { ApiError, api } from "@/lib/api";
import { formatMoneyShort } from "@/lib/format";
import type { Project } from "@/lib/types";

export const dynamic = "force-dynamic";

const STAGE_ICON = {
  intake: Tray,
  extraction: ListChecks,
  quote: Table,
  proposal: FileText,
} as const;

function greeting(name: string): string {
  const hour = new Date().getHours();
  const part = hour < 12 ? "Morning" : hour < 18 ? "Afternoon" : "Evening";
  return `${part}, ${name.split(" ")[0]}`;
}

/** What this bid is actually waiting on, in the estimator's words. */
function waitingOn(project: Project): { tag: string; colour: string; soft: string } {
  if (project.activeJob)
    return { tag: "Claude is reading", colour: "var(--app-warn)", soft: "var(--app-warn-soft)" };
  if (project.counts.needsLook > 0)
    return {
      tag: `${project.counts.needsLook} to check`,
      colour: "var(--app-neg)",
      soft: "var(--app-neg-soft)",
    };
  if (project.documentCount === 0)
    return { tag: "Needs documents", colour: "var(--app-tx-3)", soft: "var(--app-panel-2)" };
  if (project.stage === "proposal")
    return { tag: "Ready to hand off", colour: "var(--app-pos)", soft: "var(--app-pos-soft)" };
  return { tag: "Ready to price", colour: "var(--app-accent)", soft: "var(--app-accent-soft)" };
}

export default async function DashboardPage() {
  const session = await auth();
  const name = session?.user?.name ?? "Estimator";

  let projects: Project[] = [];
  let apiError: string | null = null;
  try {
    projects = (await api.get<{ projects: Project[] }>("/api/projects")).projects;
  } catch (error) {
    apiError = error instanceof ApiError ? error.message : String(error);
  }

  const needsLook = projects.reduce((sum, project) => sum + project.counts.needsLook, 0);
  const running = projects.filter((project) => project.activeJob).length;
  const openValue = projects.reduce((sum, project) => sum + (project.quoteTotal ?? 0), 0);
  const handedOff = projects.filter((project) => project.handedOffTo).length;

  // Most urgent first: flagged work, then anything Claude is mid-way through.
  const queue = [...projects].sort((a, b) => {
    const score = (p: Project) => (p.counts.needsLook > 0 ? 0 : p.activeJob ? 1 : 2);
    return score(a) - score(b);
  });

  const cleared = projects.reduce((sum, p) => sum + p.counts.clear, 0);
  const total = projects.reduce((sum, p) => sum + p.counts.total, 0);
  const focusPct = total ? Math.round((cleared / total) * 100) : 0;

  return (
    <>
      <PageHeader crumbs={[{ label: "Workspace" }, { label: "Dashboard" }]} reviewCount={needsLook} />

      <main className="min-h-0 flex-1 overflow-auto p-6">
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-[24px] font-semibold">
              {greeting(name)} <span>👋</span>
            </h1>
            <p className="mt-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
              {needsLook > 0
                ? `${needsLook} line${needsLook === 1 ? "" : "s"} are waiting on you across ${projects.length} bid${projects.length === 1 ? "" : "s"}.`
                : "Nothing is flagged. Bid documents in, priced proposal out."}
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div
              className="flex items-center gap-2.5 rounded-lg px-3 py-2"
              style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
            >
              <Buildings size={16} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
              <span className="flex flex-col leading-tight">
                <span className="text-[10px] uppercase tracking-[0.07em]" style={{ color: "var(--app-tx-3)" }}>
                  Current workspace
                </span>
                <span className="text-[12.5px] font-semibold">Hamilton Parker · CBC</span>
              </span>
            </div>
            <NewBidDialog />
          </div>
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

        <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 300px" }}>
          <section
            className="overflow-hidden rounded-xl"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            <div
              className="flex items-center gap-2.5 border-b px-4 py-3.5"
              style={{ borderColor: "var(--app-line)" }}
            >
              <ListChecks size={17} weight="duotone" style={{ color: "var(--app-accent)" }} />
              <span className="text-[15px] font-semibold">Your queue</span>
              <span className="flex-1" />
              <Link
                href="/bids"
                className="text-[12px] no-underline"
                style={{ color: "var(--app-tx-2)" }}
              >
                Open the bid board →
              </Link>
            </div>

            {queue.length === 0 ? (
              <div className="grid place-items-center gap-1.5 px-6 py-16 text-center">
                <span className="text-[13.5px] font-semibold">Nothing in the queue</span>
                <span className="max-w-[380px] text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                  Create a bid and drop the plan set in to get started.
                </span>
              </div>
            ) : (
              queue.map((project) => {
                const Icon = STAGE_ICON[project.stage];
                const state = waitingOn(project);
                return (
                  <Link
                    key={project.id}
                    href={`/bids/${project.code}/${project.stage}`}
                    className="flex items-center gap-3 border-b px-4 py-3 no-underline last:border-b-0 hover:bg-[var(--app-panel-2)]"
                    style={{ borderColor: "var(--app-line)" }}
                  >
                    <span
                      className="grid h-8 w-8 shrink-0 place-items-center rounded-lg"
                      style={{ background: state.soft, color: state.colour }}
                    >
                      <Icon size={16} weight="duotone" />
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col leading-tight">
                      <span className="truncate text-[13px] font-semibold">{project.name}</span>
                      <span className="truncate text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                        {project.code}
                        {project.gc ? ` · ${project.gc}` : ""}
                        {project.location ? ` · ${project.location}` : ""}
                      </span>
                    </span>
                    <span
                      className="shrink-0 rounded-full px-2.5 py-1 text-[11px]"
                      style={{ background: state.soft, color: state.colour }}
                    >
                      {state.tag}
                    </span>
                    <span
                      className="tnum w-[92px] shrink-0 text-right text-[11.5px]"
                      style={{ color: "var(--app-tx-3)" }}
                    >
                      {project.bidDue
                        ? `due ${new Date(project.bidDue).toLocaleDateString()}`
                        : "no due date"}
                    </span>
                    <CaretRight size={13} weight="bold" style={{ color: "var(--app-tx-3)" }} />
                  </Link>
                );
              })
            )}
          </section>

          <aside className="flex flex-col gap-3">
            <div
              className="rounded-xl p-4"
              style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
            >
              <div className="flex items-center gap-2">
                <Timer size={15} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
                <span className="text-[13px] font-semibold">Focus</span>
              </div>

              <div className="mt-4 grid place-items-center">
                <div
                  className="grid h-[110px] w-[110px] place-items-center rounded-full"
                  style={{
                    background: `conic-gradient(var(--app-accent) ${focusPct * 3.6}deg, var(--app-panel-2) 0deg)`,
                  }}
                >
                  <div
                    className="grid h-[86px] w-[86px] place-items-center rounded-full"
                    style={{ background: "var(--app-panel)" }}
                  >
                    <span className="flex flex-col items-center leading-tight">
                      <span className="tnum text-[22px] font-bold">{focusPct}%</span>
                      <span className="text-[10px]" style={{ color: "var(--app-tx-3)" }}>
                        lines cleared
                      </span>
                    </span>
                  </div>
                </div>
              </div>

              <p className="mt-4 text-[12.5px] font-semibold">
                {needsLook > 0 ? `${needsLook} still need a look` : "Everything is checked"}
              </p>
              <p className="mt-0.5 text-[11.5px]" style={{ color: "var(--app-tx-2)" }}>
                {cleared} of {total} extracted lines confirmed across every open bid.
              </p>
            </div>

            <div
              className="rounded-xl p-4"
              style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
            >
              {[
                { label: "Open bids", value: String(projects.length), Icon: Buildings },
                {
                  label: "Claude running",
                  value: String(running),
                  Icon: Lightning,
                  tone: running ? "var(--app-warn)" : undefined,
                },
                {
                  label: "Lines to check",
                  value: String(needsLook),
                  Icon: WarningCircle,
                  tone: needsLook ? "var(--app-neg)" : undefined,
                },
                { label: "Handed to sales", value: String(handedOff), Icon: FileText },
                { label: "Quoted value", value: formatMoneyShort(openValue), Icon: Table },
              ].map((tile) => (
                <div
                  key={tile.label}
                  className="flex items-center gap-2.5 border-b py-2.5 last:border-b-0"
                  style={{ borderColor: "var(--app-line)" }}
                >
                  <tile.Icon size={14} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
                  <span className="flex-1 text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                    {tile.label}
                  </span>
                  <span
                    className="tnum text-[14px] font-semibold"
                    style={{ color: tile.tone ?? "var(--app-tx)" }}
                  >
                    {tile.value}
                  </span>
                </div>
              ))}
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}
