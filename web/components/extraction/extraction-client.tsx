"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import {
  ArrowsClockwise,
  Checks,
  FilePdf,
  ListChecks,
  ArrowRight,
  ArrowLeft,
  Lightning,
  X,
  PhoneCall,
} from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import dynamic from "next/dynamic";

import { AlternateBar } from "@/components/bids/alternate-bar";
import { BulkBar } from "@/components/extraction/bulk-bar";
import { LineItemRow, ROW_COLUMNS } from "@/components/extraction/line-item-row";
import { PartComposer } from "@/components/extraction/part-composer";
import { useRowKeys } from "@/hooks/use-row-keys";
import { useUiState } from "@/components/shell/ui-state";
import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import type {
  AlternateAssignResult,
  AlternatesResponse,
  BidDocument,
  BulkResult,
  Job,
  LineItem,
  LineItemsResponse,
} from "@/lib/types";

// pdf.js touches DOMMatrix at module scope, so the viewer cannot be evaluated
// during server rendering.
const SheetViewer = dynamic(
  () => import("@/components/extraction/sheet-viewer").then((m) => m.SheetViewer),
  {
    ssr: false,
    loading: () => (
      <aside
        className="grid h-[320px] w-full shrink-0 place-items-center rounded-xl xl:h-auto xl:w-[clamp(380px,34vw,560px)]"
        style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
      >
        <span className="text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Loading the sheet viewer…
        </span>
      </aside>
    ),
  },
);

const FILTERS = [
  { key: "all", label: "All", countKey: "all" },
  { key: "needs_look", label: "Needs a look", countKey: "needs_look" },
  { key: "duplicate", label: "Duplicates", countKey: "duplicate" },
  { key: "by_hand", label: "By hand", countKey: "by_hand" },
  { key: "clear", label: "Clear", countKey: "clear" },
] as const;

export function ExtractionClient({
  code,
  documents,
  initialJob,
}: {
  code: string;
  documents: BidDocument[];
  initialJob: Job | null;
}) {
  const router = useRouter();
  const { openNotes, focusMode } = useUiState();
  const [filter, setFilter] = useState<string>("all");
  const [selected, setSelected] = useState<LineItem | null>(null);
  const [showSheet, setShowSheet] = useState(true);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [alternate, setAlternate] = useState<string | null | undefined>(undefined);
  const [runDismissed, setRunDismissed] = useState<string | null>(null);

  // Poll while Claude is working so the screen fills in as it goes.
  const { data: jobData } = useSWR<{ jobs: Job[] }>(
    `/api/proxy/jobs?project=${code}&limit=1`,
    proxyFetcher,
    {
      refreshInterval: (latest) => {
        const current = latest?.jobs?.[0] ?? initialJob;
        return current?.status === "running" || current?.status === "queued" ? 4000 : 0;
      },
      fallbackData: initialJob ? { jobs: [initialJob] } : undefined,
    },
  );
  const job = jobData?.jobs?.[0] ?? null;
  const running = job?.status === "running" || job?.status === "queued";

  const alternateQuery =
    alternate === undefined ? "" : `&alternate=${encodeURIComponent(alternate ?? "")}`;

  const { data, error, isLoading, mutate } = useSWR<LineItemsResponse>(
    `/api/proxy/projects/${code}/line-items?filter=${filter}${alternateQuery}`,
    proxyFetcher,
    { refreshInterval: running ? 4000 : 0 },
  );

  const { data: alternateData, mutate: mutateAlternates } = useSWR<AlternatesResponse>(
    `/api/proxy/projects/${code}/alternates`,
    proxyFetcher,
  );

  const refresh = useCallback(() => {
    mutate();
    mutateAlternates();
    router.refresh();
  }, [mutate, mutateAlternates, router]);

  const items = data?.lineItems ?? [];
  const counts = data?.counts;
  const needsLook = counts?.needs_look ?? 0;

  const togglePick = useCallback((item: LineItem) => {
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(item.id)) next.delete(item.id);
      else next.add(item.id);
      return next;
    });
  }, []);

  const confirmOne = useCallback(
    async (item: LineItem) => {
      try {
        await proxyMutate(`/api/proxy/projects/${code}/line-items/${item.id}/confirm`);
        mutate();
      } catch (problem) {
        toast.error("Could not confirm that line", { description: errorMessage(problem) });
      }
    },
    [code, mutate],
  );

  const { cursorId } = useRowKeys<LineItem>({
    rows: items,
    onConfirm: confirmOne,
    onToggleSelect: togglePick,
    onOpen: (item) => {
      setSelected(item);
      setShowSheet(true);
    },
  });

  async function assignAlternate(alternateName: string | null) {
    if (picked.size === 0) return;
    setBusy(true);
    try {
      const result = await proxyMutate<AlternateAssignResult>(
        `/api/proxy/projects/${code}/alternates/assign`,
        { body: { ids: [...picked], alternate: alternateName, scope: "line-items" } },
      );
      toast.success(`Moved ${result.moved} line${result.moved === 1 ? "" : "s"}`);
      setPicked(new Set());
      refresh();
    } catch (problem) {
      toast.error("Could not move those lines", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  async function bulk(action: "confirm" | "delete") {
    // Removing a batch of lines is not undoable from this screen.
    if (
      action === "delete" &&
      !window.confirm(
        `Remove ${picked.size} line${picked.size === 1 ? "" : "s"} from this bid? This cannot be undone here.`,
      )
    ) {
      return;
    }

    setBusy(true);
    try {
      const result = await proxyMutate<BulkResult>(
        `/api/proxy/projects/${code}/line-items/bulk`,
        { body: { ids: [...picked], action } },
      );
      toast.success(
        action === "confirm" ? `${result.affected} confirmed` : `${result.affected} removed`,
      );
      setPicked(new Set());
      refresh();
    } catch (problem) {
      toast.error("That did not go through", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  const progressLabel = useMemo(() => {
    if (!counts) return "loading…";
    return `${counts.clear} of ${counts.all} items clear`;
  }, [counts]);

  async function post(path: string, success: string, then?: () => void) {
    setBusy(true);
    try {
      await proxyMutate(`/api/proxy/projects/${code}${path}`);
      toast.success(success);
      refresh();
      then?.();
    } catch (problem) {
      toast.error("That did not go through", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-4 xl:flex-row">
        <section className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
          <div
            className="flex flex-col rounded-xl"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            <div
              className="flex flex-wrap items-center gap-3 border-b px-4 py-3.5"
              style={{ borderColor: "var(--app-line)" }}
            >
              <span
                className="grid h-8 w-8 shrink-0 place-items-center rounded-lg"
                style={{ background: "var(--app-accent-soft)", color: "var(--app-accent)" }}
              >
                <ListChecks size={17} weight="duotone" />
              </span>
              <span className="flex flex-col leading-tight">
                <span className="text-[15px] font-semibold">Line items</span>
                <span className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
                  {progressLabel} · <b>J</b> <b>K</b> to move · <b>space</b> select ·{" "}
                  <b>&#8629;</b> confirm · <b>O</b> open the sheet · <b>C</b> log a call
                </span>
              </span>

              <span className="flex-1" />

              <button
                onClick={() => post("/line-items/rerun", "Claude is re-reading the drawings")}
                disabled={busy || running}
                className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] disabled:opacity-50"
                style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
              >
                <ArrowsClockwise size={14} weight="duotone" />
                Re-run extraction
              </button>

              {needsLook > 0 && (
                <button
                  onClick={() => post("/line-items/confirm-all", "Everything flagged is confirmed")}
                  disabled={busy}
                  className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-semibold disabled:opacity-50"
                  style={{ background: "var(--app-accent)", color: "#fff" }}
                >
                  <Checks size={14} weight="duotone" />
                  Confirm all {needsLook}
                </button>
              )}

              <button
                onClick={() => setShowSheet((current) => !current)}
                className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px]"
                style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
              >
                <FilePdf size={14} weight="duotone" />
                {showSheet ? "Hide the sheet" : "Open the sheet"}
              </button>
            </div>

            <div className="flex flex-wrap gap-1 px-3 py-2">
              {FILTERS.map((entry) => {
                const active = filter === entry.key;
                const count = counts?.[entry.countKey as keyof typeof counts] ?? 0;
                return (
                  <button
                    key={entry.key}
                    onClick={() => setFilter(entry.key)}
                    className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px]"
                    style={{
                      background: active ? "var(--app-panel-2)" : "transparent",
                      color: active ? "var(--app-tx)" : "var(--app-tx-2)",
                      border: `1px solid ${active ? "var(--app-line)" : "transparent"}`,
                    }}
                  >
                    {entry.label}
                    <span className="tnum" style={{ color: "var(--app-tx-3)" }}>
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <AlternateBar code={code} active={alternate} onChange={setAlternate} />

          {running && (
            <div
              className="anim-fadein relative overflow-hidden rounded-xl px-4 py-3 text-[12.5px]"
              style={{
                background: "var(--app-warn-soft)",
                border: "1px solid var(--app-warn-line)",
                color: "var(--app-warn)",
              }}
            >
              <span className="anim-sweep" />
              Claude is reading the bid set. Lines appear here as they are found.
            </div>
          )}

          {job?.status === "done" && job.note && runDismissed !== job.id && !focusMode && (
            <div
              className="anim-fadein flex items-center gap-2.5 rounded-xl px-4 py-2.5"
              style={{
                background: "var(--app-pos-soft)",
                border: "1px solid var(--app-pos)",
                color: "var(--app-pos)",
              }}
            >
              <Lightning size={15} weight="duotone" />
              <span className="flex flex-1 flex-col leading-tight">
                <span className="text-[12.5px] font-semibold">Last pass complete</span>
                <span className="text-[11.5px]">{job.note}</span>
              </span>
              <button onClick={() => setRunDismissed(job.id)} aria-label="Dismiss the run status">
                <X size={13} weight="bold" />
              </button>
            </div>
          )}

          {job?.status === "failed" && (
            <div
              className="rounded-xl px-4 py-3 text-[12.5px]"
              style={{
                background: "var(--app-neg-soft)",
                border: "1px solid var(--app-neg-line)",
                color: "var(--app-neg)",
              }}
            >
              <strong>The last run failed.</strong> {job.error}
            </div>
          )}

          <div
            className="min-h-[200px] flex-1 overflow-auto rounded-xl"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            <div style={{ minWidth: 760 }}>
            <div
              className="sticky top-0 z-10 grid gap-3 border-b px-4 py-2.5 text-[10.5px] uppercase tracking-[0.07em]"
              style={{
                gridTemplateColumns: ROW_COLUMNS,
                borderColor: "var(--app-line)",
                background: "var(--app-panel)",
                color: "var(--app-tx-3)",
              }}
            >
              <span>
                <input
                  type="checkbox"
                  aria-label="Select all"
                  checked={items.length > 0 && picked.size === items.length}
                  onChange={() =>
                    setPicked(
                      picked.size === items.length ? new Set() : new Set(items.map((i) => i.id)),
                    )
                  }
                />
              </span>
              <span />
              <span>Mark</span>
              <span>Description</span>
              <span>Size</span>
              <span>Qty</span>
              <span>HW set</span>
              <span className="text-right">Status</span>
            </div>

            {error ? (
              <div className="grid place-items-center gap-2 px-6 py-16 text-center">
                <span className="text-[13.5px] font-semibold" style={{ color: "var(--app-neg)" }}>
                  Could not load the line items
                </span>
                <span className="max-w-[420px] text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                  {errorMessage(error)}
                </span>
                <button
                  onClick={() => mutate()}
                  className="mt-1 rounded-md px-3 py-1.5 text-[12px]"
                  style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
                >
                  Try again
                </button>
              </div>
            ) : isLoading && !data ? (
              <div className="grid place-items-center px-6 py-16 text-center">
                <span className="text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
                  Loading the openings…
                </span>
              </div>
            ) : items.length === 0 ? (
              <div className="grid place-items-center gap-1.5 px-6 py-16 text-center">
                <span className="text-[13.5px] font-semibold">
                  {running ? "Reading the bid set…" : "Nothing here yet"}
                </span>
                <span className="max-w-[420px] text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                  {running
                    ? "Claude is working through the schedules and elevations."
                    : filter === "all"
                      ? "Upload a plan set on the intake step, and the openings are read for you."
                      : "No lines match this filter."}
                </span>
              </div>
            ) : (
              items.map((item) => (
                <LineItemRow
                  key={item.id}
                  item={item}
                  code={code}
                  selected={selected?.id === item.id}
                  focused={cursorId === item.id}
                  picked={picked.has(item.id)}
                  onPick={() => togglePick(item)}
                  onSelect={(next) => {
                    setSelected(next);
                    if (next) setShowSheet(true);
                  }}
                  onChanged={refresh}
                />
              ))
            )}
            </div>
            <BulkBar
              selected={picked.size}
              total={items.length}
              busy={busy}
              alternates={alternateData?.alternates}
              onSelectAll={() => setPicked(new Set(items.map((i) => i.id)))}
              onConfirm={() => bulk("confirm")}
              onRemove={() => bulk("delete")}
              onClear={() => setPicked(new Set())}
              onAssignAlternate={assignAlternate}
            />
          </div>

          <PartComposer code={code} onAdded={refresh} />
        </section>

        {showSheet && (
          <SheetViewer
            code={code}
            documents={documents}
            selected={selected}
            onClose={() => setShowSheet(false)}
          />
        )}
      </main>

      <footer
        className="flex shrink-0 flex-wrap items-center gap-3 border-t px-5 py-3"
        style={{ borderColor: "var(--app-line)", background: "var(--app-bg)" }}
      >
        <a
          href={`/bids/${code}/intake`}
          className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px] no-underline"
          style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
        >
          <ArrowLeft size={14} weight="bold" />
          Back
        </a>

        <button
          onClick={() => openNotes("Extraction & entry")}
          className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px]"
          style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
        >
          <PhoneCall size={14} weight="duotone" />
          Log a call
        </button>

        <span
          className="min-w-[200px] flex-1 text-[12.5px]"
          style={{ color: "var(--app-tx-2)" }}
        >
          {needsLook > 0
            ? `${needsLook} item${needsLook === 1 ? "" : "s"} need a look. Open one, check it against the sheet, confirm.`
            : counts?.all
              ? "Every line has been checked."
              : "No lines yet."}
        </span>

        <button
          onClick={() => post("/line-items/rerun", "Re-extraction queued")}
          disabled={busy || running}
          className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px] disabled:opacity-50"
          style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
        >
          <ArrowsClockwise size={14} weight="duotone" />
          Re-run extraction
        </button>

        <button
          onClick={() =>
            post("/line-items/continue-to-quote", "Pricing queued for Claude", () =>
              router.push(`/bids/${code}/quote`),
            )
          }
          disabled={busy || !counts?.all}
          className="flex items-center gap-1.5 rounded-md px-4 py-2 text-[12.5px] font-semibold disabled:opacity-50"
          style={{ background: "var(--app-accent)", color: "#fff" }}
        >
          Continue to Quote
          <ArrowRight size={14} weight="bold" />
        </button>
      </footer>
    </>
  );
}
