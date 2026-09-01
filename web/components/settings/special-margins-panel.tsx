"use client";

import { useState } from "react";
import useSWR from "swr";
import { UserFocus, Plus, Trash, Warning } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import type { SpecialMargins } from "@/lib/types";

const SPECIAL_URL = "/api/proxy/reference/special-margins";

function asPercent(margin: number): string {
  const pct = margin * 100;
  return `${pct.toFixed(pct % 1 === 0 ? 0 : 1)}%`;
}

/**
 * Edit special-customer margins (NR-9). A margin here is a sourcing-driven
 * override the pricing pass applies for that customer, with the note as its
 * recorded reason (margin-governance). Values are PENDING from CBC until entered.
 * Writes reference-library/multipliers/special_customer_margins.json.
 */
export function SpecialMarginsPanel() {
  const { data, error, isLoading, mutate } = useSWR<SpecialMargins>(SPECIAL_URL, proxyFetcher);
  const [busy, setBusy] = useState(false);
  const [newName, setNewName] = useState("");
  const [newMargin, setNewMargin] = useState("");
  const [newNote, setNewNote] = useState("");

  async function save(body: Record<string, unknown>, success: string) {
    setBusy(true);
    try {
      await proxyMutate<SpecialMargins>(SPECIAL_URL, { method: "PATCH", body });
      toast.success(success);
      mutate();
    } catch (problem) {
      toast.error("Could not save that margin", { description: errorMessage(problem) });
      mutate();
    } finally {
      setBusy(false);
    }
  }

  function commitMargin(name: string, raw: string, current: number | null) {
    if (raw.trim() === "") {
      if (current === null) return;
      save({ customers: [{ name, margin: null }] }, `${name} margin cleared`);
      return;
    }
    const next = Number(raw);
    if (Number.isNaN(next) || next < 0 || next >= 1) {
      toast.error("Margin must be a fraction between 0 and 1", {
        description: `e.g. 0.30 for 30%. Got "${raw}".`,
      });
      mutate();
      return;
    }
    const rounded = Math.round(next * 10000) / 10000;
    if (rounded === current) return;
    save({ customers: [{ name, margin: rounded }] }, `${name} set to ${asPercent(rounded)}`);
  }

  function commitNote(name: string, raw: string, current: string) {
    if (raw.trim() === current.trim()) return;
    save({ customers: [{ name, note: raw.trim() }] }, `${name} reason updated`);
  }

  function add(event: React.FormEvent) {
    event.preventDefault();
    const name = newName.trim();
    if (!name) {
      toast.error("Give the customer a name");
      return;
    }
    let margin: number | null = null;
    if (newMargin.trim() !== "") {
      const parsed = Number(newMargin);
      if (Number.isNaN(parsed) || parsed < 0 || parsed >= 1) {
        toast.error("Margin must be a fraction between 0 and 1", { description: "e.g. 0.30 for 30%." });
        return;
      }
      margin = Math.round(parsed * 10000) / 10000;
    }
    save(
      { customers: [{ name, margin, note: newNote.trim() || null }] },
      `${name} added`,
    );
    setNewName("");
    setNewMargin("");
    setNewNote("");
  }

  function remove(name: string) {
    if (!window.confirm(`Remove ${name} from special-customer margins?`)) return;
    save({ remove: [name] }, `${name} removed`);
  }

  const customers = data?.customers ?? [];

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <div className="flex items-center gap-2">
          <UserFocus size={16} weight="duotone" style={{ color: "var(--app-accent)" }} />
          <h2 className="text-[15px] font-semibold">Special-customer margins</h2>
        </div>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          A sourcing-driven margin override for a named account, with its reason recorded. Applied by
          the pricing pass; below-band lines are still flagged, not blocked. Administrators only.
        </p>
      </div>

      {error && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-neg)" }}>
          Could not read the special margins: {errorMessage(error)}
        </p>
      )}
      {isLoading && !data && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Loading…
        </p>
      )}

      {data && (
        <div className="divide-y" style={{ borderColor: "var(--app-line)" }}>
          {customers.map((customer) => (
            <div key={customer.name} className="px-4 py-3" style={{ borderColor: "var(--app-line)" }}>
              <div className="flex items-center gap-3">
                <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">
                  {customer.name}
                </span>
                <span
                  className="tnum shrink-0 text-[11.5px]"
                  style={{ color: customer.margin === null ? "var(--app-warn, var(--app-neg))" : "var(--app-tx-3)", width: "72px", textAlign: "right" }}
                >
                  {customer.margin === null ? "PENDING" : `= ${asPercent(customer.margin)}`}
                </span>
                <input
                  key={`${customer.name}-${customer.margin}`}
                  type="number"
                  step="0.01"
                  min="0"
                  max="0.99"
                  defaultValue={customer.margin ?? ""}
                  disabled={busy}
                  placeholder="unset"
                  aria-label={`${customer.name} margin fraction`}
                  onBlur={(event) => commitMargin(customer.name, event.target.value, customer.margin)}
                  className="tnum w-23 shrink-0 rounded-md px-2.5 py-1.5 text-right text-[12.5px] outline-none focus:ring-2"
                  style={{
                    background: "var(--app-panel-2)",
                    border: "1px solid var(--app-line)",
                    color: "var(--app-tx)",
                  }}
                />
                <button
                  type="button"
                  onClick={() => remove(customer.name)}
                  disabled={busy}
                  aria-label={`Remove ${customer.name}`}
                  className="shrink-0 rounded-md p-1.5"
                  style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-3)" }}
                >
                  <Trash size={14} />
                </button>
              </div>
              <input
                key={`${customer.name}-note-${customer.note ?? ""}`}
                defaultValue={customer.note ?? ""}
                disabled={busy}
                placeholder="Reason for the override (recorded)"
                aria-label={`${customer.name} override reason`}
                onBlur={(event) => commitNote(customer.name, event.target.value, customer.note ?? "")}
                className="mt-2 w-full rounded-md px-2.5 py-1.5 text-[11.5px] outline-none focus:ring-2"
                style={{
                  background: "var(--app-panel-2)",
                  border: "1px solid var(--app-line)",
                  color: "var(--app-tx-2)",
                }}
              />
            </div>
          ))}
        </div>
      )}

      {data && (
        <form
          onSubmit={add}
          className="flex flex-col gap-2 border-t px-4 py-3"
          style={{ borderColor: "var(--app-line)" }}
        >
          <div className="flex items-end gap-2">
            <label className="flex min-w-0 flex-1 flex-col">
              <span className="text-[10.5px] uppercase tracking-[0.07em]" style={{ color: "var(--app-tx-3)" }}>
                Customer
              </span>
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                placeholder="e.g. Wendys"
                aria-label="New customer name"
                className="mt-0.5 rounded-md px-2.5 py-1.5 text-[12.5px] outline-none focus:ring-2"
                style={{
                  background: "var(--app-panel-2)",
                  border: "1px solid var(--app-line)",
                  color: "var(--app-tx)",
                }}
              />
            </label>
            <label className="flex flex-col">
              <span className="text-[10.5px] uppercase tracking-[0.07em]" style={{ color: "var(--app-tx-3)" }}>
                Margin
              </span>
              <input
                value={newMargin}
                onChange={(event) => setNewMargin(event.target.value)}
                type="number"
                step="0.01"
                min="0"
                max="0.99"
                placeholder="optional"
                aria-label="New customer margin"
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
              Add
            </button>
          </div>
          <input
            value={newNote}
            onChange={(event) => setNewNote(event.target.value)}
            placeholder="Reason for the override (recorded)"
            aria-label="New customer override reason"
            className="rounded-md px-2.5 py-1.5 text-[11.5px] outline-none focus:ring-2"
            style={{
              background: "var(--app-panel-2)",
              border: "1px solid var(--app-line)",
              color: "var(--app-tx-2)",
            }}
          />
        </form>
      )}

      {data?.rule && (
        <p
          className="flex items-start gap-1.5 border-t px-4 py-2.5 text-[11px]"
          style={{ borderColor: "var(--app-line)", color: "var(--app-tx-3)" }}
        >
          <Warning size={13} weight="fill" style={{ color: "var(--app-warn, var(--app-neg))", marginTop: 1, flexShrink: 0 }} />
          {data.rule}
        </p>
      )}
    </section>
  );
}
