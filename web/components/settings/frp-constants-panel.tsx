"use client";

import { useState } from "react";
import useSWR from "swr";
import { GridNine } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import type { FrpConstants } from "@/lib/types";

const FRP_URL = "/api/proxy/reference/frp-constants";

type FieldKey =
  | "panel_size"
  | "waste_pct"
  | "trim_stick_length"
  | "adhesive_coverage_sqft_per_unit"
  | "opening_handling";

const FIELDS: { key: FieldKey; label: string; numeric: boolean; noteKey: keyof FrpConstants; placeholder: string }[] = [
  { key: "panel_size", label: "Panel size", numeric: false, noteKey: "panel_size_note", placeholder: "4 x 8" },
  { key: "waste_pct", label: "Waste %", numeric: true, noteKey: "waste_pct_note", placeholder: "10" },
  { key: "trim_stick_length", label: "Trim stick length (ft)", numeric: true, noteKey: "trim_stick_length_note", placeholder: "8" },
  {
    key: "adhesive_coverage_sqft_per_unit",
    label: "Adhesive coverage (sq ft/unit)",
    numeric: true,
    noteKey: "adhesive_coverage_note",
    placeholder: "200",
  },
  { key: "opening_handling", label: "Opening handling", numeric: false, noteKey: "opening_handling_note", placeholder: "Deduct openings over 2 sq ft" },
];

/**
 * Enter the FRP geometry-to-quantity constants (Open Item 5). Until every one is
 * set the take-off reports geometry only and quantities stay null - a guessed
 * panel size or waste factor is a confidently wrong quote. Writes
 * reference-library/frp_constants/conversion_constants.json.
 */
export function FrpConstantsPanel() {
  const { data, error, isLoading, mutate } = useSWR<FrpConstants>(FRP_URL, proxyFetcher);
  const [busy, setBusy] = useState(false);

  async function save(body: Record<string, unknown>, success: string) {
    setBusy(true);
    try {
      await proxyMutate<FrpConstants>(FRP_URL, { method: "PATCH", body });
      toast.success(success);
      mutate();
    } catch (problem) {
      toast.error("Could not save that constant", { description: errorMessage(problem) });
      mutate();
    } finally {
      setBusy(false);
    }
  }

  function commit(key: FieldKey, numeric: boolean, raw: string, current: string | number | null) {
    const trimmed = raw.trim();
    if (numeric) {
      if (trimmed === "") {
        if (current === null) return;
        save({ [key]: null }, `${key} cleared`);
        return;
      }
      const next = Number(trimmed);
      if (Number.isNaN(next) || next < 0) {
        toast.error("Must be a number of 0 or more", { description: `Got "${raw}".` });
        mutate();
        return;
      }
      if (next === current) return;
      save({ [key]: next }, "Saved");
    } else {
      const value = trimmed || null;
      if (value === (current ?? null)) return;
      save({ [key]: value }, "Saved");
    }
  }

  const isSet = data?.status === "SET";

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <GridNine size={16} weight="duotone" style={{ color: "var(--app-accent)" }} />
            <h2 className="text-[15px] font-semibold">FRP conversion constants</h2>
          </div>
          {data && (
            <span
              className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
              style={
                isSet
                  ? { background: "var(--app-pos-soft, var(--app-accent-soft))", color: "var(--app-pos, var(--app-accent))" }
                  : { background: "var(--app-warn-soft, var(--app-neg-soft))", color: "var(--app-warn, var(--app-neg))" }
              }
            >
              {isSet ? "Set" : "Pending"}
            </span>
          )}
        </div>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Geometry-to-quantity conversion for FRP panels (Open Item 5). Administrators only.
        </p>
      </div>

      {error && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-neg)" }}>
          Could not read the constants: {errorMessage(error)}
        </p>
      )}
      {isLoading && !data && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Loading…
        </p>
      )}

      {data && !isSet && (
        <p
          className="mx-4 mt-3 rounded-md px-3 py-2 text-[11px]"
          style={{ background: "var(--app-warn-soft, var(--app-neg-soft))", border: "1px solid var(--app-neg-line)", color: "var(--app-warn, var(--app-neg))" }}
        >
          Until every constant is set, the FRP take-off reports geometry only and leaves quantities
          null. It will not guess.
        </p>
      )}

      {data && (
        <div className="flex flex-col gap-3 p-4">
          {FIELDS.map((field) => {
            const current = data[field.key] as string | number | null;
            const note = data[field.noteKey] as string | undefined;
            return (
              <label key={field.key} className="flex flex-col gap-1">
                <span className="text-[12px] font-medium">{field.label}</span>
                <input
                  key={`${field.key}-${current ?? ""}`}
                  type={field.numeric ? "number" : "text"}
                  step={field.numeric ? "0.01" : undefined}
                  min={field.numeric ? "0" : undefined}
                  defaultValue={current ?? ""}
                  disabled={busy}
                  placeholder={field.placeholder}
                  aria-label={field.label}
                  onBlur={(event) => commit(field.key, field.numeric, event.target.value, current)}
                  className="rounded-md px-2.5 py-1.5 text-[12.5px] outline-none focus:ring-2"
                  style={{
                    background: "var(--app-panel-2)",
                    border: "1px solid var(--app-line)",
                    color: "var(--app-tx)",
                  }}
                />
                {note && (
                  <span className="text-[10.5px]" style={{ color: "var(--app-tx-3)" }}>
                    {note}
                  </span>
                )}
              </label>
            );
          })}
        </div>
      )}
    </section>
  );
}
