"use client";

import { useState } from "react";
import useSWR from "swr";
import { Stack, Plus, Trash } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { formatMoney } from "@/lib/format";
import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import type { ManualAdders } from "@/lib/types";

const ADDERS_URL = "/api/proxy/reference/adders";

/**
 * Edit the Hager list adders (NR-4). These are LIST dollar amounts the pricing
 * pass multiplies by the base item's category multiplier - they are never in a
 * price-book lookup. Writes reference-library/adders/manual_adders.json, which the
 * next pricing run reads.
 */
export function AddersPanel() {
  const { data, error, isLoading, mutate } = useSWR<ManualAdders>(ADDERS_URL, proxyFetcher);
  const [busy, setBusy] = useState(false);
  const [newName, setNewName] = useState("");
  const [newAmount, setNewAmount] = useState("");

  async function save(body: Record<string, unknown>, success: string) {
    setBusy(true);
    try {
      await proxyMutate<ManualAdders>(ADDERS_URL, { method: "PATCH", body });
      toast.success(success);
      mutate();
    } catch (problem) {
      toast.error("Could not save that adder", { description: errorMessage(problem) });
      mutate();
    } finally {
      setBusy(false);
    }
  }

  function commit(name: string, raw: string, current: number) {
    const next = Number(raw);
    if (raw.trim() === "" || Number.isNaN(next) || next < 0) {
      toast.error("Adder must be a dollar amount of 0 or more", { description: `Got "${raw}".` });
      mutate();
      return;
    }
    const rounded = Math.round(next * 100) / 100;
    if (rounded === current) return;
    save({ items: { [name]: rounded } }, `${name} set to $${formatMoney(rounded)}`);
  }

  function add(event: React.FormEvent) {
    event.preventDefault();
    const name = newName.trim();
    const amount = Number(newAmount);
    if (!name) {
      toast.error("Give the adder a name");
      return;
    }
    if (newAmount.trim() === "" || Number.isNaN(amount) || amount < 0) {
      toast.error("Adder must be a dollar amount of 0 or more");
      return;
    }
    save({ items: { [name]: Math.round(amount * 100) / 100 } }, `${name} added`);
    setNewName("");
    setNewAmount("");
  }

  function remove(name: string) {
    if (!window.confirm(`Remove the "${name}" adder?`)) return;
    save({ remove: [name] }, `${name} removed`);
  }

  const items = data?.hagerListAdders.items ?? [];

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <div className="flex items-center gap-2">
          <Stack size={16} weight="duotone" style={{ color: "var(--app-accent)" }} />
          <h2 className="text-[15px] font-semibold">Manual adders</h2>
        </div>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Hager list adders, in dollars — added on top of the base price, then multiplied by the
          item&apos;s category multiplier. Never part of a price-book lookup (NR-4). Administrators
          only.
        </p>
      </div>

      {error && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-neg)" }}>
          Could not read the adders: {errorMessage(error)}
        </p>
      )}
      {isLoading && !data && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Loading…
        </p>
      )}

      {data && (
        <div className="divide-y" style={{ borderColor: "var(--app-line)" }}>
          {items.map((item) => (
            <div
              key={item.name}
              className="flex items-center gap-3 px-4 py-2.5"
              style={{ borderColor: "var(--app-line)" }}
            >
              <span className="min-w-0 flex-1 truncate text-[13px]">{item.name}</span>
              <span className="tnum shrink-0 text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
                $
              </span>
              <input
                key={`${item.name}-${item.list_adder}`}
                type="number"
                step="0.01"
                min="0"
                defaultValue={item.list_adder}
                disabled={busy}
                aria-label={`${item.name} list adder`}
                onBlur={(event) => commit(item.name, event.target.value, item.list_adder)}
                className="tnum w-24 shrink-0 rounded-md px-2.5 py-1.5 text-right text-[12.5px] outline-none focus:ring-2"
                style={{
                  background: "var(--app-panel-2)",
                  border: "1px solid var(--app-line)",
                  color: "var(--app-tx)",
                }}
              />
              <button
                type="button"
                onClick={() => remove(item.name)}
                disabled={busy}
                aria-label={`Remove ${item.name}`}
                className="shrink-0 rounded-md p-1.5"
                style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-3)" }}
              >
                <Trash size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {data && (
        <form
          onSubmit={add}
          className="flex items-end gap-2 border-t px-4 py-3"
          style={{ borderColor: "var(--app-line)" }}
        >
          <label className="flex min-w-0 flex-1 flex-col">
            <span className="text-[10.5px] uppercase tracking-[0.07em]" style={{ color: "var(--app-tx-3)" }}>
              Adder
            </span>
            <input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="e.g. Lead lined"
              aria-label="New adder name"
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
              List $
            </span>
            <input
              value={newAmount}
              onChange={(event) => setNewAmount(event.target.value)}
              type="number"
              step="0.01"
              min="0"
              placeholder="0.00"
              aria-label="New adder list amount"
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
        </form>
      )}

      {data && data.adderTypes.length > 0 && (
        <div className="border-t px-4 py-3" style={{ borderColor: "var(--app-line)" }}>
          <span className="text-[10.5px] uppercase tracking-[0.07em]" style={{ color: "var(--app-tx-3)" }}>
            Adder categories (no single value — priced per series)
          </span>
          <ul className="mt-1.5 flex flex-col gap-1">
            {data.adderTypes.map((type) => (
              <li key={type.type} className="text-[11.5px]" style={{ color: "var(--app-tx-2)" }}>
                <span className="font-medium capitalize">{type.type}</span>
                {type.note.includes("PENDING") && (
                  <span
                    className="ml-1.5 rounded-full px-1.5 py-0.5 text-[9.5px] font-semibold uppercase"
                    style={{ background: "var(--app-warn-soft, var(--app-neg-soft))", color: "var(--app-warn, var(--app-neg))" }}
                  >
                    Pending CBC
                  </span>
                )}
                <span style={{ color: "var(--app-tx-3)" }}> — {type.note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
