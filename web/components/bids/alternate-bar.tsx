"use client";

import { useState } from "react";
import useSWR from "swr";
import { Plus, Warning } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { formatMoneyShort } from "@/lib/api";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export interface Alternate {
  name: string | null;
  label: string;
  isBase: boolean;
  lineItemCount: number;
  quoteLineCount: number;
  subtotal: number;
  grandTotal: number;
  unpricedLines: number;
}

/**
 * Base bid and alternates as distinct, comparable groups.
 *
 * That comparability is the whole point: an estimator quotes the base and each
 * alternate separately so a GC can price the options against each other. How a
 * reconciliation actually resolves is still an open question with CBC, so this
 * shows the groups and says so rather than implying an answer.
 */
export function AlternateBar({
  code,
  active,
  onChange,
  showTotals = false,
}: {
  code: string;
  /** null = base bid; undefined = everything. */
  active: string | null | undefined;
  onChange: (next: string | null | undefined) => void;
  showTotals?: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const { data, mutate } = useSWR<{ alternates: Alternate[]; pending: string }>(
    `/api/proxy/projects/${code}/alternates`,
    fetcher,
  );

  const alternates = data?.alternates ?? [];
  // With no alternates there is nothing to compare, so stay out of the way.
  if (alternates.length <= 1 && !adding) {
    return (
      <button
        onClick={() => setAdding(true)}
        className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11.5px]"
        style={{ border: "1px dashed var(--app-line)", color: "var(--app-tx-3)" }}
      >
        <Plus size={12} weight="bold" />
        Add an alternate
      </button>
    );
  }

  async function create(name: string) {
    if (!name.trim()) return;
    const response = await fetch(`/api/proxy/projects/${code}/alternates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      toast.error("Could not add that alternate", { description: String(body.detail) });
      return;
    }
    toast.success(`${name.trim()} created`, {
      description: "Empty by design — move lines into it, or add them by hand.",
    });
    setAdding(false);
    mutate();
    onChange(name.trim());
  }

  return (
    <div
      className="flex flex-wrap items-center gap-1.5 rounded-xl px-3 py-2"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <span
        className="mr-1 text-[10.5px] uppercase tracking-[0.07em]"
        style={{ color: "var(--app-tx-3)" }}
      >
        Groups
      </span>

      <button
        onClick={() => onChange(undefined)}
        className="rounded-md px-2.5 py-1 text-[12px]"
        style={{
          background: active === undefined ? "var(--app-panel-2)" : "transparent",
          border: `1px solid ${active === undefined ? "var(--app-line)" : "transparent"}`,
          color: active === undefined ? "var(--app-tx)" : "var(--app-tx-2)",
        }}
      >
        All
      </button>

      {alternates.map((alternate) => {
        const on = active === alternate.name;
        return (
          <button
            key={alternate.label}
            onClick={() => onChange(alternate.name)}
            className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12px]"
            style={{
              background: on ? "var(--app-accent-soft)" : "transparent",
              border: `1px solid ${on ? "var(--app-accent-line)" : "var(--app-line)"}`,
              color: on ? "var(--app-accent)" : "var(--app-tx-2)",
            }}
          >
            {alternate.label}
            {showTotals ? (
              <span className="tnum" style={{ color: "var(--app-tx-3)" }}>
                {alternate.grandTotal ? formatMoneyShort(alternate.grandTotal) : "—"}
              </span>
            ) : (
              <span className="tnum" style={{ color: "var(--app-tx-3)" }}>
                {alternate.lineItemCount}
              </span>
            )}
          </button>
        );
      })}

      {adding ? (
        <input
          autoFocus
          placeholder="Alternate 1"
          onKeyDown={(event) => {
            if (event.key === "Enter") create(event.currentTarget.value);
            if (event.key === "Escape") setAdding(false);
          }}
          onBlur={() => setAdding(false)}
          className="w-[120px] rounded-md px-2 py-1 text-[12px] outline-none"
          style={{
            background: "var(--app-panel-2)",
            border: "1px solid var(--app-accent-line)",
            color: "var(--app-tx)",
          }}
        />
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="rounded-md px-2 py-1 text-[12px]"
          style={{ border: "1px dashed var(--app-line)", color: "var(--app-tx-3)" }}
        >
          <Plus size={12} weight="bold" />
        </button>
      )}

      <span className="flex-1" />

      <span
        className="flex items-center gap-1.5 text-[10.5px]"
        style={{ color: "var(--app-warn)" }}
        title={data?.pending}
      >
        <Warning size={12} weight="duotone" />
        Reconciliation rules pending
      </span>
    </div>
  );
}
