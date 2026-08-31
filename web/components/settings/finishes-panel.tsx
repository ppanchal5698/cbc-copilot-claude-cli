"use client";

import { useState } from "react";
import useSWR from "swr";
import { Swatches, Plus, Trash, Warning } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import type { FinishCrosswalk } from "@/lib/types";

const FINISHES_URL = "/api/proxy/reference/finishes";

/**
 * Edit the dual finish crosswalk (NR-3) - US26D <-> 626, and so on. Read by the
 * matcher to reconcile nomenclature; US19 and US26D are DIFFERENT satins and must
 * stay distinct. Writes reference-library/finishes/finish_crosswalk.json.
 */
export function FinishesPanel() {
  const { data, error, isLoading, mutate } = useSWR<FinishCrosswalk>(FINISHES_URL, proxyFetcher);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({ us_code: "", numeric_code: "", description: "" });

  async function save(body: Record<string, unknown>, success: string) {
    setBusy(true);
    try {
      await proxyMutate<FinishCrosswalk>(FINISHES_URL, { method: "PATCH", body });
      toast.success(success);
      mutate();
    } catch (problem) {
      toast.error("Could not save that finish", { description: errorMessage(problem) });
      mutate();
    } finally {
      setBusy(false);
    }
  }

  function commitField(us_code: string, field: "numeric_code" | "description", raw: string, current: string) {
    const next = raw.trim();
    if (next === current.trim()) return;
    save({ finishes: [{ us_code, [field]: next || null }] }, `${us_code} updated`);
  }

  function togglePremium(us_code: string, current: boolean) {
    save({ finishes: [{ us_code, premium: !current }] }, `${us_code} marked ${!current ? "premium" : "standard"}`);
  }

  function add(event: React.FormEvent) {
    event.preventDefault();
    const us_code = draft.us_code.trim();
    if (!us_code) {
      toast.error("Give the finish a US code, e.g. US26D");
      return;
    }
    save(
      {
        finishes: [
          {
            us_code,
            numeric_code: draft.numeric_code.trim() || null,
            description: draft.description.trim() || null,
            premium: false,
          },
        ],
      },
      `${us_code} added`,
    );
    setDraft({ us_code: "", numeric_code: "", description: "" });
  }

  function remove(us_code: string) {
    if (!window.confirm(`Remove the ${us_code} finish mapping?`)) return;
    save({ remove: [us_code] }, `${us_code} removed`);
  }

  const inputStyle = {
    background: "var(--app-panel-2)",
    border: "1px solid var(--app-line)",
    color: "var(--app-tx)",
  };
  const finishes = data?.finishes ?? [];

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <div className="flex items-center gap-2">
          <Swatches size={16} weight="duotone" style={{ color: "var(--app-accent)" }} />
          <h2 className="text-[15px] font-semibold">Finish crosswalk</h2>
        </div>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Dual nomenclature the matcher reconciles — US code ↔ numeric (BHMA). Administrators only.
        </p>
      </div>

      {error && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-neg)" }}>
          Could not read the crosswalk: {errorMessage(error)}
        </p>
      )}
      {isLoading && !data && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Loading…
        </p>
      )}

      {data?.warning && (
        <p
          className="mx-4 mt-3 flex items-start gap-1.5 rounded-md px-3 py-2 text-[11px]"
          style={{ background: "var(--app-neg-soft)", border: "1px solid var(--app-neg-line)", color: "var(--app-neg)" }}
        >
          <Warning size={13} weight="fill" style={{ marginTop: 1, flexShrink: 0 }} />
          {data.warning}
        </p>
      )}

      {data && (
        <div className="mt-2 divide-y" style={{ borderColor: "var(--app-line)" }}>
          {finishes.map((finish) => (
            <div
              key={finish.us_code}
              className="flex flex-wrap items-center gap-2 px-4 py-2.5"
              style={{ borderColor: "var(--app-line)" }}
            >
              <span className="w-16 shrink-0 text-[12.5px] font-semibold">{finish.us_code}</span>
              <input
                key={`${finish.us_code}-num-${finish.numeric_code ?? ""}`}
                defaultValue={finish.numeric_code ?? ""}
                disabled={busy}
                placeholder="numeric"
                aria-label={`${finish.us_code} numeric code`}
                onBlur={(event) => commitField(finish.us_code, "numeric_code", event.target.value, finish.numeric_code ?? "")}
                className="tnum w-16 rounded-md px-2 py-1.5 text-[12px] outline-none focus:ring-2"
                style={inputStyle}
              />
              <input
                key={`${finish.us_code}-desc-${finish.description ?? ""}`}
                defaultValue={finish.description ?? ""}
                disabled={busy}
                placeholder="description"
                aria-label={`${finish.us_code} description`}
                onBlur={(event) => commitField(finish.us_code, "description", event.target.value, finish.description ?? "")}
                className="min-w-0 flex-1 rounded-md px-2 py-1.5 text-[12px] outline-none focus:ring-2"
                style={inputStyle}
              />
              <button
                type="button"
                onClick={() => togglePremium(finish.us_code, finish.premium ?? false)}
                disabled={busy}
                aria-pressed={finish.premium ?? false}
                className="shrink-0 rounded-md px-2 py-1 text-[10.5px] font-semibold uppercase"
                style={{
                  border: "1px solid var(--app-line)",
                  background: finish.premium ? "var(--app-accent-soft)" : "transparent",
                  color: finish.premium ? "var(--app-accent)" : "var(--app-tx-3)",
                }}
              >
                Premium
              </button>
              <button
                type="button"
                onClick={() => remove(finish.us_code)}
                disabled={busy}
                aria-label={`Remove ${finish.us_code}`}
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
          className="flex flex-wrap items-end gap-2 border-t px-4 py-3"
          style={{ borderColor: "var(--app-line)" }}
        >
          <input
            value={draft.us_code}
            onChange={(event) => setDraft((d) => ({ ...d, us_code: event.target.value }))}
            placeholder="US code"
            aria-label="New finish US code"
            className="w-24 rounded-md px-2.5 py-1.5 text-[12.5px] outline-none focus:ring-2"
            style={inputStyle}
          />
          <input
            value={draft.numeric_code}
            onChange={(event) => setDraft((d) => ({ ...d, numeric_code: event.target.value }))}
            placeholder="Numeric"
            aria-label="New finish numeric code"
            className="w-20 rounded-md px-2.5 py-1.5 text-[12.5px] outline-none focus:ring-2"
            style={inputStyle}
          />
          <input
            value={draft.description}
            onChange={(event) => setDraft((d) => ({ ...d, description: event.target.value }))}
            placeholder="Description"
            aria-label="New finish description"
            className="min-w-0 flex-1 rounded-md px-2.5 py-1.5 text-[12.5px] outline-none focus:ring-2"
            style={inputStyle}
          />
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
    </section>
  );
}
