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
  FloppyDisk,
  PencilLine,
  Clock,
  PhoneCall,
} from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { AlternateBar } from "@/components/bids/alternate-bar";
import { useUiState } from "@/components/shell/ui-state";
import { formatMoney, formatPercent } from "@/lib/api";
import type { Job, QuoteLine, QuoteResponse } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const TAX_OPTIONS = [
  { key: "OH", label: "Ohio 8.0%" },
  { key: "KY", label: "Kentucky 6.5%" },
  // "NONE" is a deliberate ruling; an unset value means the ship-to state decides.
  { key: "NONE", label: "No nexus" },
];

/** An input that only commits on blur or Enter, so totals do not thrash per keystroke. */
function Cell({
  value,
  onCommit,
  align = "right",
  prefix,
  suffix,
  disabled,
}: {
  value: number | null;
  onCommit: (next: number | null) => void;
  align?: "left" | "right";
  prefix?: string;
  suffix?: string;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState<string>(value === null ? "" : String(value));
  const [editing, setEditing] = useState(false);

  if (!editing && draft !== (value === null ? "" : String(value))) {
    setDraft(value === null ? "" : String(value));
  }

  function commit() {
    setEditing(false);
    const trimmed = draft.trim();
    if (trimmed === "") {
      if (value !== null) onCommit(null);
      return;
    }
    const parsed = Number(trimmed);
    if (Number.isNaN(parsed) || parsed === value) return;
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
        value={draft}
        disabled={disabled}
        onChange={(event) => setDraft(event.target.value)}
        onFocus={() => setEditing(true)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            setDraft(value === null ? "" : String(value));
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
  const { openNotes } = useUiState();
  const [busy, setBusy] = useState(false);

  const { data: jobData } = useSWR<{ jobs: Job[] }>(
    `/api/proxy/jobs?project=${code}&limit=1`,
    fetcher,
    { refreshInterval: 4000, fallbackData: initialJob ? { jobs: [initialJob] } : undefined },
  );
  const job = jobData?.jobs?.[0] ?? null;
  const running = job?.status === "running" || job?.status === "queued";

  const { data, mutate } = useSWR<QuoteResponse>(
    `/api/proxy/projects/${code}/quote`,
    fetcher,
    { refreshInterval: running ? 4000 : 0 },
  );

  const refresh = useCallback(() => {
    mutate();
    router.refresh();
  }, [mutate, router]);

  const totals = data?.totals;
  const groups = data?.groups ?? [];

  async function patchLine(line: QuoteLine, body: Record<string, unknown>) {
    const response = await fetch(`/api/proxy/projects/${code}/quote/lines/${line.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({ detail: response.statusText }));
      toast.error("Could not save that", { description: String(detail.detail) });
      return;
    }
    mutate();
  }

  async function deleteLine(line: QuoteLine) {
    const response = await fetch(`/api/proxy/projects/${code}/quote/lines/${line.id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      toast.error("Could not remove that line");
      return;
    }
    toast.success("Line removed");
    mutate();
  }

  async function addLine() {
    const response = await fetch(`/api/proxy/projects/${code}/quote/lines`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "New line", division: "08 11 00", qty: 1 }),
    });
    if (!response.ok) {
      toast.error("Could not add a line");
      return;
    }
    toast.success("Line added", { description: "Set its cost and margin." });
    mutate();
  }

  async function setFreight(value: number | null) {
    await fetch(`/api/proxy/projects/${code}/quote/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ freight: value }),
    });
    toast.success(value ? "Freight added to the quote" : "Freight back to TBD");
    mutate();
  }

  async function setTax(state: string) {
    await fetch(`/api/proxy/projects/${code}/quote/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taxJurisdiction: state }),
    });
    mutate();
  }

  async function continueToProposal() {
    setBusy(true);
    const response = await fetch(`/api/proxy/projects/${code}/quote/continue-to-proposal`, {
      method: "POST",
    });
    setBusy(false);
    if (!response.ok) {
      toast.error("Could not hand off to the proposal");
      return;
    }
    toast.success("Proposal queued for Claude");
    refresh();
    router.push(`/bids/${code}/proposal`);
  }

  return (
    <>
      <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4">
        <AlternateBar code={code} active={undefined} onChange={() => undefined} showTotals />

        <div
          className="flex flex-col rounded-xl"
          style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
        >
          <div
            className="flex items-center gap-3 border-b px-4 py-3.5"
            style={{ borderColor: "var(--app-line)" }}
          >
            <span
              className="grid h-8 w-8 place-items-center rounded-lg"
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
                {data.edited!.count} line{data.edited!.count === 1 ? "" : "s"} edited by hand
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

            <div className="flex gap-1">
              {TAX_OPTIONS.map((option) => {
                const active = (totals?.taxJurisdiction ?? "") === option.key;
                return (
                  <button
                    key={option.key || "none"}
                    onClick={() => setTax(option.key)}
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

          <div
            className="grid gap-3 border-b px-4 py-2.5 text-[10.5px] uppercase tracking-[0.07em]"
            style={{
              gridTemplateColumns: "140px 1fr 60px 95px 85px 72px 120px 105px 30px",
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

          {groups.length === 0 && (
            <div className="grid place-items-center gap-1.5 px-6 py-16 text-center">
              <span className="text-[13.5px] font-semibold">
                {running ? "Pricing in progress…" : "Nothing priced yet"}
              </span>
              <span className="max-w-[440px] text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                {running
                  ? "Claude is working through the catalog and the price books."
                  : "Confirm the openings on the extraction step, then hand off to pricing."}
              </span>
            </div>
          )}

          {groups.map((group) => (
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
                    gridTemplateColumns: "140px 1fr 60px 95px 85px 72px 120px 105px 30px",
                    borderColor: "var(--app-line)",
                    borderLeft: line.addedByHand ? "3px solid var(--app-neg)" : undefined,
                  }}
                >
                  <span className="truncate text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                    {line.part ?? "—"}
                  </span>

                  <span className="min-w-0">
                    <span className="block truncate text-[12.5px]">{line.description}</span>
                    {(line.marginOverridden || line.addedByHand) && (
                      <span className="text-[10.5px]" style={{ color: "var(--app-neg)" }}>
                        {line.addedByHand ? "added by hand" : "margin overridden"}
                        {line.overrideReason ? ` · ${line.overrideReason}` : ""}
                      </span>
                    )}
                  </span>

                  <Cell
                    value={line.qty}
                    onCommit={(next) => patchLine(line, { qty: next ?? 1 })}
                  />
                  <Cell
                    value={line.cost}
                    prefix="$"
                    onCommit={(next) => patchLine(line, { cost: next })}
                  />

                  <span className="tnum text-right text-[12.5px]">
                    {line.sell === null ? (
                      <span
                        className="rounded px-1.5 py-0.5 text-[10.5px]"
                        style={{ background: "var(--app-warn-soft)", color: "var(--app-warn)" }}
                      >
                        {line.priceStatus ?? "MANUAL"}
                      </span>
                    ) : (
                      formatMoney(line.sell)
                    )}
                  </span>

                  <Cell
                    value={line.margin === null ? null : Math.round(line.margin * 100)}
                    suffix="%"
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
                        style={{ background: "var(--app-warn-soft)", color: "var(--app-warn)" }}
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
                    aria-label="Remove line"
                    style={{ color: "var(--app-tx-3)" }}
                  >
                    <Trash size={14} weight="duotone" />
                  </button>
                </div>
              ))}
            </div>
          ))}

          {totals && (
            <div
              className="flex items-end gap-8 border-t px-4 py-4"
              style={{ borderColor: "var(--app-line)" }}
            >
              <span className="flex-1 text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
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
                <Cell
                  value={totals.freight}
                  prefix="$"
                  onCommit={(next) => setFreight(next)}
                />
                <span className="mt-0.5 text-[10px]" style={{ color: "var(--app-tx-3)" }}>
                  {totals.freight ? "quoted on this bid" : "TBD at estimate stage"}
                </span>
              </span>

              <span className="flex flex-col items-end leading-tight">
                <span
                  className="text-[10.5px] uppercase tracking-[0.07em]"
                  style={{ color: "var(--app-tx-3)" }}
                >
                  Sell total
                </span>
                <span className="tnum text-[24px] font-bold">
                  ${formatMoney(totals.grandTotal)}
                </span>
              </span>
            </div>
          )}
        </div>
      </main>

      <footer
        className="flex shrink-0 items-center gap-3 border-t px-5 py-3"
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

        <span className="flex-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
          Cost, sell and margin are all editable. Overrides are logged against your name.
        </span>
        <button
          onClick={() => mutate()}
          className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px]"
          style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
        >
          <FloppyDisk size={14} weight="duotone" />
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
