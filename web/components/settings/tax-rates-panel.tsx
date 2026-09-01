"use client";

import { useState } from "react";
import useSWR from "swr";
import { MapPinLine, Plus, Trash } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import type { TaxRates } from "@/lib/types";

const TAX_URL = "/api/proxy/reference/tax";

function asPercent(rate: number): string {
  const pct = rate * 100;
  return `${pct.toFixed(pct % 1 === 0 ? 0 : 2)}%`;
}

/**
 * Edit nexus sales-tax rates. Writes reference-library/tax/sales_tax_rates.json
 * through the API, which the pricing engine re-reads on change. States absent
 * from the table are untaxed by design - this lists only where CBC has nexus.
 */
export function TaxRatesPanel() {
  const { data, error, isLoading, mutate } = useSWR<TaxRates>(TAX_URL, proxyFetcher);
  const [busy, setBusy] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newRate, setNewRate] = useState("");

  async function save(body: Record<string, unknown>, success: string) {
    setBusy(true);
    try {
      await proxyMutate<TaxRates>(TAX_URL, { method: "PATCH", body });
      toast.success(success);
      mutate();
    } catch (problem) {
      toast.error("Could not save that tax rate", { description: errorMessage(problem) });
      mutate();
    } finally {
      setBusy(false);
    }
  }

  function commit(code: string, raw: string, current: number) {
    const next = Number(raw);
    if (raw.trim() === "" || Number.isNaN(next) || next < 0 || next >= 1) {
      toast.error("Tax rate must be a fraction between 0 and 1", {
        description: `e.g. 0.08 for 8%. Got "${raw}".`,
      });
      mutate();
      return;
    }
    const rounded = Math.round(next * 100000) / 100000;
    if (rounded === current) return;
    save({ rates: { [code]: rounded } }, `${code} set to ${asPercent(rounded)}`);
  }

  function add(event: React.FormEvent) {
    event.preventDefault();
    const code = newCode.trim().toUpperCase();
    const rate = Number(newRate);
    if (!/^[A-Z]{2}$/.test(code)) {
      toast.error("Enter a two-letter state code", { description: `Got "${newCode}".` });
      return;
    }
    if (newRate.trim() === "" || Number.isNaN(rate) || rate < 0 || rate >= 1) {
      toast.error("Rate must be a fraction between 0 and 1", { description: "e.g. 0.08 for 8%." });
      return;
    }
    save({ rates: { [code]: rate } }, `${code} added at ${asPercent(rate)}`);
    setNewCode("");
    setNewRate("");
  }

  function remove(code: string) {
    if (!window.confirm(`Remove ${code}? CBC would no longer charge tax there (0% rate).`)) return;
    save({ remove: [code] }, `${code} removed`);
  }

  const entries = Object.entries(data?.rates ?? {}).sort(([a], [b]) => a.localeCompare(b));

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <div className="flex items-center gap-2">
          <MapPinLine size={16} weight="duotone" style={{ color: "var(--app-accent)" }} />
          <h2 className="text-[15px] font-semibold">Sales tax by jurisdiction</h2>
        </div>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Rates for the states where CBC has nexus. Every other state and Canada is untaxed. Applied
          from the ship-to location; an unknown project state stays UNRESOLVED, never zero.
          Administrators only.
        </p>
      </div>

      {error && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-neg)" }}>
          Could not read the tax table: {errorMessage(error)}
        </p>
      )}
      {isLoading && !data && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Loading…
        </p>
      )}

      {data && (
        <div className="divide-y" style={{ borderColor: "var(--app-line)" }}>
          {entries.map(([code, rate]) => (
            <div
              key={code}
              className="flex items-center gap-4 px-4 py-3"
              style={{ borderColor: "var(--app-line)" }}
            >
              <span className="w-12 shrink-0 text-[13px] font-semibold">{code}</span>
              <span className="flex-1 text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
                = {asPercent(rate)}
              </span>
              <input
                key={`${code}-${rate}`}
                type="number"
                step="0.001"
                min="0"
                max="0.99"
                defaultValue={rate}
                disabled={busy}
                aria-label={`${code} tax rate fraction`}
                onBlur={(event) => commit(code, event.target.value, rate)}
                className="tnum w-23 shrink-0 rounded-md px-2.5 py-1.5 text-right text-[12.5px] outline-none focus:ring-2"
                style={{
                  background: "var(--app-panel-2)",
                  border: "1px solid var(--app-line)",
                  color: "var(--app-tx)",
                }}
              />
              <button
                type="button"
                onClick={() => remove(code)}
                disabled={busy}
                aria-label={`Remove ${code}`}
                className="shrink-0 rounded-md p-1.5"
                style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-3)" }}
              >
                <Trash size={14} />
              </button>
            </div>
          ))}
          {entries.length === 0 && (
            <p className="px-4 py-4 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
              No nexus jurisdictions on file — every quote is untaxed.
            </p>
          )}
        </div>
      )}

      {data && (
        <form
          onSubmit={add}
          className="flex items-end gap-2 border-t px-4 py-3"
          style={{ borderColor: "var(--app-line)" }}
        >
          <label className="flex flex-col">
            <span className="text-[10.5px] uppercase tracking-[0.07em]" style={{ color: "var(--app-tx-3)" }}>
              State
            </span>
            <input
              value={newCode}
              onChange={(event) => setNewCode(event.target.value.toUpperCase().slice(0, 2))}
              placeholder="IN"
              aria-label="New jurisdiction state code"
              className="mt-0.5 w-16 rounded-md px-2.5 py-1.5 text-[12.5px] uppercase outline-none focus:ring-2"
              style={{
                background: "var(--app-panel-2)",
                border: "1px solid var(--app-line)",
                color: "var(--app-tx)",
              }}
            />
          </label>
          <label className="flex flex-col">
            <span className="text-[10.5px] uppercase tracking-[0.07em]" style={{ color: "var(--app-tx-3)" }}>
              Rate (fraction)
            </span>
            <input
              value={newRate}
              onChange={(event) => setNewRate(event.target.value)}
              type="number"
              step="0.001"
              min="0"
              max="0.99"
              placeholder="0.07"
              aria-label="New jurisdiction tax rate"
              className="tnum mt-0.5 w-24 rounded-md px-2.5 py-1.5 text-right text-[12.5px] outline-none focus:ring-2"
              style={{
                background: "var(--app-panel-2)",
                border: "1px solid var(--app-line)",
                color: "var(--app-tx)",
              }}
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px] font-semibold"
            style={{ background: "var(--app-accent)", color: "#fff" }}
          >
            <Plus size={13} weight="bold" />
            Add jurisdiction
          </button>
        </form>
      )}
    </section>
  );
}
