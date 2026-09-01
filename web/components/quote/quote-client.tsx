"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import {
  Table,
  Plus,
  Trash,
  ArrowRight,
  ArrowLeft,
  ArrowsClockwise,
  PencilLine,
  Clock,
  PhoneCall,
} from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { AlternateBar } from "@/components/bids/alternate-bar";
import { JobFailedBanner } from "@/components/jobs/job-failed-banner";
import { useUiState } from "@/components/shell/ui-state";
import { formatMoney, formatPercent } from "@/lib/format";
import { belowBandTitle, isBelowBand } from "@/lib/margin";
import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import { endpoints } from "@/lib/endpoints";
import type { AlternatesResponse, IntegrationsResponse, Job, QuoteLine, QuoteResponse } from "@/lib/types";

const TAX_OPTIONS = [
  { key: "OH", label: "Ohio 8.0%" },
  { key: "KY", label: "Kentucky 6.5%" },
  // "NONE" is a deliberate ruling; an unset value means the ship-to state decides.
  { key: "NONE", label: "No nexus" },
];

const COLUMNS = "140px minmax(200px,1fr) 60px 95px 85px 72px 120px 105px 30px";

/** An input that only commits on blur or Enter, so totals do not thrash per keystroke. */
function Cell({
  value,
  onCommit,
  align = "right",
  prefix,
  suffix,
  label,
  disabled,
}: {
  value: number | null;
  onCommit: (next: number | null) => void;
  align?: "left" | "right";
  prefix?: string;
  suffix?: string;
  label: string;
  disabled?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [edit, setEdit] = useState<{ from: number | null; text: string } | null>(null);

  // The draft follows the server value unless it is being typed into. Derived
  // from the value it was seeded off rather than synced in an effect, so a
  // background poll can never overwrite what someone is halfway through typing.
  const text = edit && (editing || edit.from === value) ? edit.text : value === null ? "" : String(value);

  function commit() {
    setEditing(false);
    const trimmed = text.trim();
    if (trimmed === "") {
      setEdit(null);
      if (value !== null) onCommit(null);
      return;
    }
    const parsed = Number(trimmed);
    if (Number.isNaN(parsed)) {
      toast.error(`${label} has to be a number`, { description: `"${trimmed}" is not one.` });
      setEdit(null);
      return;
    }
    setEdit(null);
    if (parsed === value) return;
    onCommit(parsed);
  }

  return (
    <span
      className="flex items-center rounded-md px-2 py-1"
      style={{ background: "var(--app-panel-2)", border: "1px solid var(--app-line)" }}
    >
      {prefix && (
        <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
          {prefix}
        </span>
      )}
      <input
        value={text}
        disabled={disabled}
        aria-label={label}
        inputMode="decimal"
        onChange={(event) => setEdit({ from: value, text: event.target.value })}
        onFocus={() => setEditing(true)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            setEdit(null);
            setEditing(false);
            event.currentTarget.blur();
          }
        }}
        placeholder="—"
        className={`tnum w-full bg-transparent text-[12.5px] outline-none ${align === "right" ? "text-right" : ""}`}
        style={{ color: "var(--app-tx)" }}
      />
      {suffix && (
        <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
          {suffix}
        </span>
      )}
    </span>
  );
}

export function QuoteClient({ code, initialJob }: { code: string; initialJob: Job | null }) {
  const router = useRouter();
  const { openNotes, userRole } = useUiState();
  const [busy, setBusy] = useState(false);
  const [alternate, setAlternate] = useState<string | null | undefined>(undefined);
  // NFR-8 is "below-band lines are flagged". The API flags them; until this
  // existed nothing showed the flag, so the guardrail ended at the API boundary.
  const [belowBandOnly, setBelowBandOnly] = useState(false);

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

  const { data, error, isLoading, mutate } = useSWR<QuoteResponse>(
    `/api/proxy/projects/${code}/quote`,
    proxyFetcher,
    { refreshInterval: running ? 4000 : 0 },
  );

  // Same SWR key as AlternateBar, so this is the same request, not a second one.
  const { data: alternateData } = useSWR<AlternatesResponse>(
    `/api/proxy/projects/${code}/alternates`,
    proxyFetcher,
  );

  const { data: integrations } = useSWR<IntegrationsResponse>(
    endpoints.integrations(),
    proxyFetcher,
  );

  const refresh = useCallback(() => {
    mutate();
    router.refresh();
  }, [mutate, router]);

  const filtering = alternate !== undefined || belowBandOnly;
  const groups = (data?.groups ?? [])
    .map((group) => {
      if (!filtering) return group;
      const lines = group.lines.filter(
        (line) =>
          (alternate === undefined ||
            (line.alternateGroup ?? null) === (alternate ?? null)) &&
          (!belowBandOnly || isBelowBand(line)),
      );
      return {
        ...group,
        lines,
        // Summing line extendeds the API already computed. No price, margin or
        // tax is recalculated here - those have one implementation, behind the API.
        subtotal: lines.reduce((sum, line) => sum + (line.extended ?? 0), 0),
      };
    })
    .filter((group) => group.lines.length > 0);

  const visibleLines = groups.reduce((sum, group) => sum + group.lines.length, 0);

  // Counted across every line the API returned, not the filtered view: a count
  // that shrank when you filtered by it would be reporting the filter.
  const belowBandTotal = (data?.groups ?? []).reduce(
    (sum, group) => sum + group.lines.filter(isBelowBand).length,
    0,
  );

  // When a group is selected the footer must show that group's money, not the
  // whole bid's. These totals are the API's own per-alternate figures.
  const selectedAlternate = filtering
    ? alternateData?.alternates.find((entry) => (entry.name ?? null) === (alternate ?? null))
    : undefined;
  const totals = data?.totals;

  async function patchLine(line: QuoteLine, body: Record<string, unknown>) {
    try {
      await proxyMutate(`/api/proxy/projects/${code}/quote/lines/${line.id}`, {
        method: "PATCH",
        body,
      });
      mutate();
    } catch (problem) {
      toast.error("Could not save that", { description: errorMessage(problem) });
    }
  }

  async function deleteLine(line: QuoteLine) {
    if (!window.confirm(`Remove "${line.description}" from the quote?`)) return;
    try {
      await proxyMutate(`/api/proxy/projects/${code}/quote/lines/${line.id}`, {
        method: "DELETE",
      });
      toast.success("Line removed");
      mutate();
    } catch (problem) {
      toast.error("Could not remove that line", { description: errorMessage(problem) });
    }
  }

  async function addLine() {
    try {
      await proxyMutate(`/api/proxy/projects/${code}/quote/lines`, {
        body: { description: "New line", division: "08 11 00", qty: 1 },
      });
      toast.success("Line added", { description: "Set its cost and margin." });
      mutate();
    } catch (problem) {
      toast.error("Could not add a line", { description: errorMessage(problem) });
    }
  }

  async function setFreight(value: number | null) {
    try {
      await proxyMutate(`/api/proxy/projects/${code}/quote/settings`, {
        method: "PATCH",
        body: { freight: value },
      });
      toast.success(value ? "Freight added to the quote" : "Freight back to TBD");
      mutate();
    } catch (problem) {
      toast.error("Could not update freight", { description: errorMessage(problem) });
    }
  }

  async function setTax(state: string) {
    try {
      await proxyMutate(`/api/proxy/projects/${code}/quote/settings`, {
        method: "PATCH",
        body: { taxJurisdiction: state },
      });
      mutate();
    } catch (problem) {
      toast.error("Could not update tax jurisdiction", { description: errorMessage(problem) });
    }
  }

  async function continueToProposal() {
    setBusy(true);
    try {
      await proxyMutate(`/api/proxy/projects/${code}/quote/continue-to-proposal`);
      toast.success("Proposal queued for Claude");
      refresh();
      router.push(`/bids/${code}/proposal`);
    } catch (problem) {
      toast.error("Could not hand off to the proposal", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  async function rerunPricing() {
    setBusy(true);
    try {
      await proxyMutate(`/api/proxy/projects/${code}/line-items/continue-to-quote`);
      toast.success("Pricing queued");
      refresh();
    } catch (problem) {
      toast.error("Could not queue pricing", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4">
        <AlternateBar code={code} active={alternate} onChange={setAlternate} showTotals />

        {job?.status === "failed" && job && (
          <JobFailedBanner
            job={job}
            role={userRole}
            stage="quote"
            onAction={(action) => {
              if (action.label === "Re-run pricing") rerunPricing();
              else if (action.label === "Notify your admin") {
                toast.message("Ask your administrator to configure the AI provider in Settings.");
              }
            }}
          />
        )}

        {running && (
          <div
            className="anim-fadein rounded-xl px-4 py-3 text-[12.5px]"
            style={{
              background: "var(--app-warn-soft)",
              border: "1px solid var(--app-warn-line)",
              color: "var(--app-warn)",
            }}
          >
            Claude is pricing the lines. Totals refresh as matches land.
          </div>
        )}

        {integrations?.p21 && !integrations.p21.connected && (
          <p
            className="rounded-xl px-4 py-3 text-[12px] leading-relaxed"
            style={{
              background: "var(--app-panel-2)",
              border: "1px solid var(--app-line)",
              color: "var(--app-tx-2)",
            }}
          >
            P21 last-PO cost (Path 1) is not connected — pricing uses list × multiplier or
            manual entry until NR-10 is resolved. See Settings for details.
          </p>
        )}

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
              <Table size={17} weight="duotone" />
            </span>
            <span className="flex flex-col leading-tight">
              <span className="text-[15px] font-semibold">Quote</span>
              <span className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
                {data?.lineCount ?? 0} lines · margin follows the category divisors
                {totals?.margin ? ` · ${formatPercent(totals.margin)} blended` : ""} · every figure
                below is editable
              </span>
            </span>

            {belowBandTotal > 0 && (
              <button
                type="button"
                onClick={() => setBelowBandOnly((on) => !on)}
                aria-pressed={belowBandOnly}
                className="rounded-lg px-2.5 py-1 text-[11.5px] font-medium transition-colors"
                style={{
                  color: belowBandOnly ? "var(--app-bg)" : "var(--app-neg)",
                  background: belowBandOnly ? "var(--app-neg)" : "transparent",
                  border: "1px solid var(--app-neg)",
                }}
                title="Lines whose margin is under its product-type floor (NFR-8)"
              >
                {belowBandTotal} below band
              </button>
            )}

            {!!data?.edited?.count && (
              <span
                className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11.5px]"
                style={{
                  background: "var(--app-neg-soft)",
                  border: "1px solid var(--app-neg-line)",
                  color: "var(--app-neg)",
                }}
              >
                <PencilLine size={13} weight="duotone" />
                {data.edited.count} line{data.edited.count === 1 ? "" : "s"} edited by hand
              </span>
            )}

            {!!data?.lapsedCount && (
              <span
                className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11.5px]"
                style={{
                  background: "var(--app-warn-soft)",
                  border: "1px solid var(--app-warn-line)",
                  color: "var(--app-warn)",
                }}
                title="Priced from a book past its 180-day review window"
              >
                <Clock size={13} weight="duotone" />
                {data.lapsedCount} lapsed
              </span>
            )}

            <span className="flex-1" />

            <div className="flex flex-wrap gap-1">
              {TAX_OPTIONS.map((option) => {
                const active = (totals?.taxJurisdiction ?? "") === option.key;
                return (
                  <button
                    key={option.key}
                    onClick={() => setTax(option.key)}
                    aria-pressed={active}
                    className="rounded-md px-2.5 py-1.5 text-[11.5px]"
                    style={{
                      background: active ? "var(--app-accent-soft)" : "transparent",
                      color: active ? "var(--app-accent)" : "var(--app-tx-2)",
                      border: `1px solid ${active ? "var(--app-accent-line)" : "var(--app-line)"}`,
                    }}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>

            <button
              onClick={addLine}
              className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px]"
              style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
            >
              <Plus size={13} weight="bold" />
              Add line
            </button>
          </div>

          {running && (
            <div
              className="anim-fadein relative overflow-hidden px-4 py-2.5 text-[12.5px]"
              style={{ background: "var(--app-warn-soft)", color: "var(--app-warn)" }}
            >
              <span className="anim-sweep" />
              Claude is matching and pricing the confirmed openings.
            </div>
          )}

          <div className="overflow-x-auto">
            <div style={{ minWidth: 940 }}>
              <div
                className="grid gap-3 border-b px-4 py-2.5 text-[10.5px] uppercase tracking-[0.07em]"
                style={{
                  gridTemplateColumns: COLUMNS,
                  borderColor: "var(--app-line)",
                  color: "var(--app-tx-3)",
                }}
              >
                <span>Part</span>
                <span>Description</span>
                <span className="text-right">Qty</span>
                <span className="text-right">Cost</span>
                <span className="text-right">Sell</span>
                <span className="text-right">Margin</span>
                <span>Basis</span>
                <span className="text-right">Extended</span>
                <span />
              </div>

              {error ? (
                <div className="grid place-items-center gap-2 px-6 py-16 text-center">
                  <span className="text-[13.5px] font-semibold" style={{ color: "var(--app-neg)" }}>
                    Could not load the quote
                  </span>
                  <span className="max-w-[440px] text-[12px]" style={{ color: "var(--app-tx-2)" }}>
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
                    Loading the priced lines…
                  </span>
                </div>
              ) : groups.length === 0 ? (
                <div className="grid place-items-center gap-1.5 px-6 py-16 text-center">
                  <span className="text-[13.5px] font-semibold">
                    {running
                      ? "Pricing in progress…"
                      : filtering && data?.lineCount
                        ? "Nothing in this group yet"
                        : "Nothing priced yet"}
                  </span>
                  <span className="max-w-[440px] text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                    {running
                      ? "Claude is working through the catalog and the price books."
                      : filtering && data?.lineCount
                        ? "Move lines into this alternate on the extraction step, or add them by hand."
                        : "Confirm the openings on the extraction step, then hand off to pricing."}
                  </span>
                </div>
              ) : (
                groups.map((group) => (
                  <div key={group.division}>
                    <div
                      className="flex items-baseline gap-2 px-4 py-2.5"
                      style={{ background: "var(--app-panel-2)" }}
                    >
                      <span className="text-[13px] font-semibold">{group.division}</span>
                      <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                        {group.lines.length} line{group.lines.length === 1 ? "" : "s"}
                      </span>
                      <span className="flex-1" />
                      <span className="tnum text-[13px] font-semibold">
                        ${formatMoney(group.subtotal)}
                      </span>
                    </div>

                    {group.lines.map((line) => (
                      <div
                        key={line.id}
                        className="grid items-center gap-3 border-b px-4 py-2 last:border-b-0"
                        style={{
                          gridTemplateColumns: COLUMNS,
                          borderColor: "var(--app-line)",
                          borderLeft: line.addedByHand ? "3px solid var(--app-neg)" : undefined,
                        }}
                      >
                        <span className="truncate text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                          {line.part ?? "—"}
                        </span>

                        <span className="min-w-0">
                          <span className="block truncate text-[12.5px]" title={line.description}>
                            {line.description}
                          </span>
                          {(line.marginOverridden || line.addedByHand) && (
                            <span className="text-[10.5px]" style={{ color: "var(--app-neg)" }}>
                              {line.addedByHand ? "added by hand" : "margin overridden"}
                              {line.overrideReason ? ` · ${line.overrideReason}` : ""}
                            </span>
                          )}
                          {isBelowBand(line) && (
                            <span
                              className="ml-1 rounded px-1 py-[1px] text-[10.5px] font-medium"
                              style={{
                                color: "var(--app-neg)",
                                border: "1px solid var(--app-neg)",
                              }}
                              title={belowBandTitle(line)}
                            >
                              below band
                            </span>
                          )}
                        </span>

                        <Cell
                          value={line.qty}
                          label={`Quantity for ${line.description}`}
                          onCommit={(next) => patchLine(line, { qty: next ?? 1 })}
                        />
                        <Cell
                          value={line.cost}
                          prefix="$"
                          label={`Cost for ${line.description}`}
                          onCommit={(next) => patchLine(line, { cost: next })}
                        />

                        <span className="tnum text-right text-[12.5px]">
                          {line.sell === null ? (
                            <span
                              className="rounded px-1.5 py-0.5 text-[10.5px]"
                              style={{
                                background: "var(--app-warn-soft)",
                                color: "var(--app-warn)",
                              }}
                            >
                              {line.priceStatus ?? "MANUAL"}
                            </span>
                          ) : (
                            formatMoney(line.sell)
                          )}
                        </span>

                        <Cell
                          // Shown to a tenth rather than rounded to a whole
                          // percent: a 27.5% band displayed as "28" and then
                          // committed back was a silent half-point of margin.
                          value={line.margin === null ? null : Number((line.margin * 100).toFixed(1))}
                          suffix="%"
                          label={`Margin for ${line.description}`}
                          onCommit={(next) =>
                            patchLine(line, {
                              margin: next === null ? null : Math.min(Math.max(next, 0), 99) / 100,
                              overrideReason: "edited on the quote grid",
                            })
                          }
                        />

                        <span className="min-w-0">
                          <span
                            className="block truncate text-[11.5px]"
                            style={{ color: "var(--app-tx-2)" }}
                            title={
                              [line.basis, line.multiplierTier, line.multiplierEffectiveDate]
                                .filter(Boolean)
                                .join(" · ") || undefined
                            }
                          >
                            {line.basis ?? "—"}
                          </span>
                          {line.lapsed && (
                            <span
                              className="rounded px-1 text-[10px]"
                              style={{
                                background: "var(--app-warn-soft)",
                                color: "var(--app-warn)",
                              }}
                              title={`Price book effective ${line.multiplierEffectiveDate} — past the 180-day review window`}
                            >
                              lapsed
                            </span>
                          )}
                        </span>

                        <span className="tnum text-right text-[12.5px] font-semibold">
                          {line.extended === null ? "—" : `$${formatMoney(line.extended)}`}
                        </span>

                        <button
                          onClick={() => deleteLine(line)}
                          aria-label={`Remove ${line.description}`}
                          style={{ color: "var(--app-tx-3)" }}
                        >
                          <Trash size={14} weight="duotone" />
                        </button>
                      </div>
                    ))}
                  </div>
                ))
              )}
            </div>
          </div>

          {totals && (
            <div
              className="flex flex-wrap items-end gap-6 border-t px-4 py-4"
              style={{ borderColor: "var(--app-line)" }}
            >
              <span className="min-w-[220px] flex-1 text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
                Lines with a magenta rule were added by hand. Divisors come from the margin sheet.
                {totals.unpricedLines > 0 && (
                  <>
                    {" "}
                    <strong style={{ color: "var(--app-warn)" }}>
                      {totals.unpricedLines === 1
                        ? "1 line still needs a price."
                        : `${totals.unpricedLines} lines still need a price.`}
                    </strong>
                  </>
                )}
              </span>

              {[
                ["Cost", `$${formatMoney(totals.cost)}`, "var(--app-tx-2)"],
                ["Margin", formatPercent(totals.margin), "var(--app-accent)"],
                [
                  `Tax ${totals.taxRate ? `${(totals.taxRate * 100).toFixed(3).replace(/0+$/, "").replace(/\.$/, "")}%` : ""}`,
                  totals.taxJurisdiction ? `$${formatMoney(totals.tax)}` : "UNRESOLVED",
                  totals.taxJurisdiction ? "var(--app-tx-2)" : "var(--app-warn)",
                ],
              ].map(([label, value, colour]) => (
                <span key={label} className="flex flex-col items-end leading-tight">
                  <span
                    className="text-[10.5px] uppercase tracking-[0.07em]"
                    style={{ color: "var(--app-tx-3)" }}
                  >
                    {label}
                  </span>
                  <span className="tnum text-[15px] font-semibold" style={{ color: colour }}>
                    {value}
                  </span>
                </span>
              ))}

              <span className="flex flex-col items-end leading-tight">
                <span
                  className="text-[10.5px] uppercase tracking-[0.07em]"
                  style={{ color: "var(--app-tx-3)" }}
                >
                  Freight
                </span>
                <Cell value={totals.freight} prefix="$" label="Freight" onCommit={setFreight} />
                <span className="mt-0.5 text-[10px]" style={{ color: "var(--app-tx-3)" }}>
                  {totals.freight ? "quoted on this bid" : "TBD at estimate stage"}
                </span>
              </span>

              <span className="flex flex-col items-end leading-tight">
                <span
                  className="text-[10.5px] uppercase tracking-[0.07em]"
                  style={{ color: "var(--app-tx-3)" }}
                >
                  {/* Showing the whole bid's total above a filtered list was
                      the screen telling two different stories at once. */}
                  {selectedAlternate ? `${selectedAlternate.label} total` : "Sell total"}
                </span>
                <span className="tnum text-[24px] font-bold">
                  $
                  {formatMoney(
                    selectedAlternate ? selectedAlternate.grandTotal : totals.grandTotal,
                  )}
                </span>
                {filtering && (
                  <span className="mt-0.5 text-[10px]" style={{ color: "var(--app-tx-3)" }}>
                    {visibleLines} of {data?.lineCount ?? 0} lines · whole bid $
                    {formatMoney(totals.grandTotal)}
                  </span>
                )}
              </span>
            </div>
          )}
        </div>
      </main>

      <footer
        className="flex flex-wrap items-center gap-3 border-t px-5 py-3"
        style={{ borderColor: "var(--app-line)", background: "var(--app-bg)" }}
      >
        <a
          href={`/bids/${code}/extraction`}
          className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px] no-underline"
          style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
        >
          <ArrowLeft size={14} weight="bold" />
          Back
        </a>
        <button
          onClick={() => openNotes("Quote")}
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
          Cost, sell and margin are all editable. Overrides are logged against your name.
        </span>
        <button
          onClick={() => mutate()}
          className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px]"
          style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
        >
          <ArrowsClockwise size={14} weight="duotone" />
          Refresh totals
        </button>
        <button
          onClick={continueToProposal}
          disabled={busy || !data?.lineCount}
          className="flex items-center gap-1.5 rounded-md px-4 py-2 text-[12.5px] font-semibold disabled:opacity-50"
          style={{ background: "var(--app-accent)", color: "#fff" }}
        >
          Continue to Proposal
          <ArrowRight size={14} weight="bold" />
        </button>
      </footer>
    </>
  );
}
