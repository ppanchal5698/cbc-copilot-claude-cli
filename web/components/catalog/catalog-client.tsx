"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Package,
  Plus,
  Trash,
  FloppyDisk,
  MagnifyingGlass,
  Lock,
} from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { AddToBid } from "@/components/catalog/add-to-bid";
import { useDebounced } from "@/hooks/use-debounced";
import { formatMoney } from "@/lib/format";
import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import type { Product, ProductSearchResponse } from "@/lib/types";

const EDIT_FIELDS = [
  { key: "description", label: "Description", type: "text" },
  { key: "manufacturer", label: "Manufacturer", type: "text" },
  { key: "division", label: "Division", type: "text" },
  { key: "cost", label: "Our cost", type: "number" },
  { key: "listPrice", label: "List", type: "number" },
  { key: "multiplier", label: "Multiplier", type: "number" },
  { key: "availability", label: "Availability", type: "text" },
] as const;

const COLUMNS = "190px minmax(220px,1fr) 130px 90px 100px 110px";

/**
 * A price means nothing without its basis. Every indexed price used to be shown as
 * "list $X"; on a vendor bought at a flat net that is the cost already, and reading
 * it as list invites multiplying it down a second time. Say which one it is, and
 * say so plainly when the sheet does not tell us.
 */
function priceLabel(product: Product): string {
  if (product.priceBasis === "net" && product.netPrice !== null && product.netPrice !== undefined) {
    return `net $${formatMoney(product.netPrice)}`;
  }
  if (product.listPrice !== null) return `list $${formatMoney(product.listPrice)}`;
  if (product.priceBasis === "unknown" && product.price !== null && product.price !== undefined) {
    return `$${formatMoney(product.price)} ?`;
  }
  return "—";
}

function draftFor(product: Product): Record<string, string> {
  return {
    description: product.description ?? "",
    manufacturer: product.manufacturer ?? "",
    division: product.division ?? "",
    cost: product.cost === null ? "" : String(product.cost),
    listPrice: product.listPrice === null ? "" : String(product.listPrice),
    multiplier: product.multiplier === null ? "" : String(product.multiplier),
    availability: product.availability ?? "",
  };
}

export function CatalogClient({ initialQuery = "" }: { initialQuery?: string }) {
  const [query, setQuery] = useState(initialQuery);
  const [division, setDivision] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [edits, setEdits] = useState<{ id: string; values: Record<string, string> } | null>(null);

  // One request once typing settles, not one per keystroke.
  const settledQuery = useDebounced(query.trim());

  const params = new URLSearchParams();
  if (settledQuery) params.set("q", settledQuery);
  if (division) params.set("division", division);

  const { data, error, isLoading, mutate } = useSWR<ProductSearchResponse>(
    `/api/proxy/catalog/products?${params.toString()}`,
    proxyFetcher,
    { keepPreviousData: true },
  );

  const products = data?.products ?? [];
  const selected = products.find((product) => product.id === selectedId) ?? null;
  // Indexed rows are rebuilt from the vendor PDF on every reindex and carry an
  // `idx:` id the API cannot resolve, so they are shown read-only rather than
  // offering a Save that returns 400.
  const editable = selected?.editable !== false;

  // The panel follows the selected row without an effect: a different part is a
  // different draft, so the identity of the row is what resets it.
  const draft = selected
    ? edits?.id === selected.id
      ? edits.values
      : draftFor(selected)
    : {};

  function setField(key: string, value: string) {
    if (!selected) return;
    setEdits({ id: selected.id, values: { ...draft, [key]: value } });
  }

  async function save() {
    if (!selected || !editable) return;
    const body: Record<string, unknown> = {};
    for (const field of EDIT_FIELDS) {
      const value = draft[field.key]?.trim() ?? "";
      body[field.key] =
        field.type === "number" ? (value === "" ? null : Number(value)) : value || null;
    }

    setBusy(true);
    try {
      await proxyMutate(`/api/proxy/catalog/products/${selected.id}`, {
        method: "PATCH",
        body,
      });
      toast.success(`${selected.part} saved`);
      setEdits(null);
      mutate();
    } catch (problem) {
      toast.error("Could not save that part", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!selected || !editable) return;
    if (
      !window.confirm(
        `Remove ${selected.part} from the catalog? Quote lines already priced from it keep their price.`,
      )
    ) {
      return;
    }

    setBusy(true);
    try {
      await proxyMutate(`/api/proxy/catalog/products/${selected.id}`, { method: "DELETE" });
      toast.success(`${selected.part} removed`);
      setSelectedId(null);
      setEdits(null);
      mutate();
    } catch (problem) {
      toast.error("Could not remove that part", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const part = String(form.get("part") ?? "").trim();

    setBusy(true);
    try {
      await proxyMutate("/api/proxy/catalog/products", {
        body: {
          part,
          description: String(form.get("description") ?? "").trim(),
          manufacturer: String(form.get("manufacturer") ?? "").trim() || null,
          division: String(form.get("division") ?? "").trim() || null,
          cost: form.get("cost") ? Number(form.get("cost")) : null,
        },
      });
      toast.success(`${part} added to the catalog`);
      setCreating(false);
      mutate();
    } catch (problem) {
      toast.error("Could not add that part", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 lg:flex-row lg:overflow-hidden">
      <section className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-[20px] font-semibold">Product catalog</h1>
            <p className="mt-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
              {data?.total ?? 0} parts · read from the price books, editable where they are yours
            </p>
          </div>
          <button
            onClick={() => setCreating((c) => !c)}
            className="flex items-center gap-1.5 rounded-md px-3.5 py-2 text-[12.5px] font-semibold"
            style={{ background: "var(--app-accent)", color: "#fff" }}
          >
            <Plus size={14} weight="bold" />
            Add part
          </button>
        </div>

        {creating && (
          <form
            onSubmit={create}
            className="anim-fadein grid gap-2 rounded-xl p-3 sm:grid-cols-2 xl:grid-cols-[170px_1fr_130px_110px_100px_90px]"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            {[
              { name: "part", placeholder: "Part number", required: true },
              { name: "description", placeholder: "Description", required: true },
              { name: "manufacturer", placeholder: "Manufacturer" },
              { name: "division", placeholder: "08 71 00" },
              { name: "cost", placeholder: "Cost", type: "number" },
            ].map((field) => (
              <input
                key={field.name}
                name={field.name}
                type={field.type ?? "text"}
                step={field.type === "number" ? "0.01" : undefined}
                required={field.required}
                placeholder={field.placeholder}
                aria-label={field.placeholder}
                className="rounded-md px-2.5 py-2 text-[12.5px] outline-none focus:ring-2"
                style={{
                  background: "var(--app-panel-2)",
                  border: "1px solid var(--app-line)",
                  color: "var(--app-tx)",
                }}
              />
            ))}
            <button
              type="submit"
              disabled={busy}
              className="rounded-md py-2 text-[12.5px] font-semibold disabled:opacity-60"
              style={{ background: "var(--app-pos)", color: "#fff" }}
            >
              Save
            </button>
          </form>
        )}

        <div
          className="flex items-center gap-2 rounded-xl px-3.5 py-2.5"
          style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
        >
          <MagnifyingGlass size={15} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Part number, description, manufacturer"
            aria-label="Search the catalog"
            className="min-w-0 flex-1 bg-transparent text-[13px] outline-none"
            style={{ color: "var(--app-tx)" }}
          />
          <span className="tnum shrink-0 text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
            {products.length} of {data?.total ?? 0}
          </span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setDivision("")}
            className="rounded-md px-3 py-1.5 text-[12px]"
            style={{
              background: division === "" ? "var(--app-accent-soft)" : "var(--app-panel)",
              color: division === "" ? "var(--app-accent)" : "var(--app-tx-2)",
              border: `1px solid ${division === "" ? "var(--app-accent-line)" : "var(--app-line)"}`,
            }}
          >
            All divisions {data?.total ?? 0}
          </button>
          {(data?.divisions ?? []).map((entry) => (
            <button
              key={entry.division}
              onClick={() => setDivision(entry.division)}
              className="rounded-md px-3 py-1.5 text-[12px]"
              style={{
                background:
                  division === entry.division ? "var(--app-accent-soft)" : "var(--app-panel)",
                color: division === entry.division ? "var(--app-accent)" : "var(--app-tx-2)",
                border: `1px solid ${division === entry.division ? "var(--app-accent-line)" : "var(--app-line)"}`,
              }}
            >
              {entry.division} {entry.count}
            </button>
          ))}
        </div>

        <div
          className="min-h-[240px] flex-1 overflow-auto rounded-xl lg:min-h-0"
          style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
        >
          <div style={{ minWidth: 840 }}>
            <div
              className="sticky top-0 z-10 grid gap-3 border-b px-4 py-2.5 text-[10.5px] uppercase tracking-[0.07em]"
              style={{
                gridTemplateColumns: COLUMNS,
                borderColor: "var(--app-line)",
                background: "var(--app-panel)",
                color: "var(--app-tx-3)",
              }}
            >
              <span>Part</span>
              <span>Description</span>
              <span>Manufacturer</span>
              <span className="text-right">Cost</span>
              <span>Division</span>
              <span>Availability</span>
            </div>

            {error ? (
              <div className="grid place-items-center gap-2 px-6 py-16 text-center">
                <span className="text-[13.5px] font-semibold" style={{ color: "var(--app-neg)" }}>
                  Could not load the catalog
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
            ) : isLoading && products.length === 0 ? (
              <div className="grid place-items-center px-6 py-16 text-center">
                <span className="text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
                  Searching the catalog…
                </span>
              </div>
            ) : products.length === 0 ? (
              <div className="grid place-items-center gap-1.5 px-6 py-16 text-center">
                <span className="text-[13.5px] font-semibold">
                  {data?.indexAvailable === false
                    ? "The catalog index has not been built"
                    : "No parts match"}
                </span>
                <span className="max-w-[460px] text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                  {/* The API says exactly why it is empty. Showing "no matches"
                      for an unbuilt index sent people looking for the wrong problem. */}
                  {data?.note ??
                    (settledQuery || division
                      ? "Nothing here matches that search. Clear the filters, or add the part by hand."
                      : "Upload a price book and Claude fills the catalog in.")}
                </span>
              </div>
            ) : (
              products.map((product) => (
                <button
                  key={product.id}
                  onClick={() => setSelectedId(product.id)}
                  aria-current={selectedId === product.id}
                  className="grid w-full items-center gap-3 border-b px-4 py-2.5 text-left last:border-b-0"
                  style={{
                    gridTemplateColumns: COLUMNS,
                    borderColor: "var(--app-line)",
                    background: selectedId === product.id ? "var(--app-panel-2)" : "transparent",
                    borderLeft:
                      selectedId === product.id
                        ? "3px solid var(--app-accent)"
                        : "3px solid transparent",
                  }}
                >
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span className="truncate text-[12.5px] font-semibold">{product.part}</span>
                    {product.editable === false && (
                      <Lock
                        size={11}
                        weight="bold"
                        style={{ color: "var(--app-tx-3)", flexShrink: 0 }}
                      />
                    )}
                  </span>
                  <span className="truncate text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
                    {product.description}
                  </span>
                  <span className="truncate text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                    {product.manufacturer ?? "—"}
                  </span>
                  <span className="tnum text-right text-[12.5px]">
                    {product.cost === null
                      ? priceLabel(product)
                      : `$${formatMoney(product.cost)}`}
                  </span>
                  <span className="tnum truncate text-[12px]" style={{ color: "var(--app-tx-3)" }}>
                    {product.division ?? "—"}
                  </span>
                  <span
                    className="truncate text-[12px]"
                    style={{
                      color:
                        product.availability?.toLowerCase().includes("long") ||
                        product.availability?.toLowerCase().includes("custom")
                          ? "var(--app-neg)"
                          : "var(--app-tx-2)",
                    }}
                  >
                    {product.availability ?? "—"}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      </section>

      <aside
        className="flex shrink-0 flex-col overflow-auto rounded-xl lg:w-[330px]"
        style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
      >
        {!selected ? (
          <div className="grid flex-1 place-items-center gap-2 px-6 py-10 text-center">
            <Package size={26} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
            <span className="text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
              Pick a part to see and edit its pricing.
            </span>
          </div>
        ) : (
          <div className="p-4">
            <span
              className="block text-[10.5px] uppercase tracking-[0.07em]"
              style={{ color: "var(--app-tx-3)" }}
            >
              {selected.manufacturer ?? "—"} · {selected.division ?? "—"}
            </span>
            <h2 className="mt-1 text-[17px] font-semibold">{selected.part}</h2>
            <p className="mt-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
              {selected.description}
            </p>

            {selected.seedSource === "prototype sample" && (
              <p
                className="mt-3 rounded-md px-2.5 py-2 text-[11px]"
                style={{
                  background: "var(--app-warn-soft)",
                  border: "1px solid var(--app-warn-line)",
                  color: "var(--app-warn)",
                }}
              >
                Sample figures from the design, not confirmed CBC pricing. Ingest the real price
                book, or correct them here.
              </p>
            )}

            {!editable ? (
              <>
                <p
                  className="mt-3 flex items-start gap-2 rounded-md px-2.5 py-2 text-[11px]"
                  style={{
                    background: "var(--app-panel-2)",
                    border: "1px solid var(--app-line)",
                    color: "var(--app-tx-2)",
                  }}
                >
                  <Lock size={13} weight="duotone" className="mt-px shrink-0" />
                  <span>
                    Read from the vendor price book, so it is not edited here — the next reindex
                    rewrites it from the PDF. Correct the sheet, or add your own part.
                  </span>
                </p>

                <div className="mt-4 flex flex-col gap-2">
                  {[
                    [
                      selected.priceBasis === "net"
                        ? "Net price"
                        : selected.priceBasis === "unknown"
                          ? "Price (basis unrecorded)"
                          : "List price",
                      priceLabel(selected).replace(/^(list|net) /, ""),
                    ],
                    ["Basis", selected.priceBasisNote ?? "—"],
                    ["Unit", selected.unit ?? "—"],
                    ["Price book", selected.priceBook ?? "—"],
                    ["Page", selected.sourcePage ? String(selected.sourcePage) : "—"],
                    ["Effective", selected.effective ?? "not recorded"],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="flex items-baseline justify-between gap-3 border-b pb-1.5 last:border-b-0"
                      style={{ borderColor: "var(--app-line)" }}
                    >
                      <span className="shrink-0 text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                        {label}
                      </span>
                      <span className="truncate text-right text-[12px]">{value}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="mt-4 flex flex-col gap-2.5">
                {EDIT_FIELDS.map((field) => (
                  <label key={field.key} className="block">
                    <span
                      className="block text-[10.5px] uppercase tracking-[0.06em]"
                      style={{ color: "var(--app-tx-3)" }}
                    >
                      {field.label}
                    </span>
                    <input
                      type={field.type}
                      step={field.type === "number" ? "0.001" : undefined}
                      value={draft[field.key] ?? ""}
                      onChange={(event) => setField(field.key, event.target.value)}
                      className="mt-1 w-full rounded-md px-2.5 py-1.5 text-[12.5px] outline-none focus:ring-2"
                      style={{
                        background: "var(--app-panel-2)",
                        border: "1px solid var(--app-line)",
                        color: "var(--app-tx)",
                      }}
                    />
                  </label>
                ))}
              </div>
            )}

            <div
              className="mt-4 flex items-baseline justify-between rounded-md px-3 py-2"
              style={{ background: "var(--app-panel-2)" }}
            >
              <span className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
                Sell at
              </span>
              <span
                className="tnum text-[14px] font-semibold"
                style={{ color: "var(--app-accent)" }}
              >
                {selected.sellAt == null ? "—" : `$${formatMoney(selected.sellAt)}`}
              </span>
            </div>
            <p className="mt-1.5 text-[11px]" style={{ color: "var(--app-tx-3)" }}>
              Sell follows the division&apos;s margin divisor. Overriding it on a quote line is
              logged against your name.
            </p>

            {(selected.xref?.length ?? 0) > 0 && (
              <div className="mt-4">
                <span
                  className="block text-[10.5px] uppercase tracking-[0.07em]"
                  style={{ color: "var(--app-tx-3)" }}
                >
                  Cross-reference
                </span>
                {selected.xref?.map((entry) => (
                  <div
                    key={`${entry.manufacturer}-${entry.part}`}
                    className="flex justify-between border-b py-1.5 last:border-b-0"
                    style={{ borderColor: "var(--app-line)" }}
                  >
                    <span className="text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                      {entry.manufacturer}
                    </span>
                    <span className="text-[12px]">{entry.part}</span>
                  </div>
                ))}
              </div>
            )}

            <AddToBid product={selected} />

            {editable && (
              <div className="mt-5 flex gap-2">
                <button
                  onClick={save}
                  disabled={busy}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-md py-2 text-[12.5px] font-semibold disabled:opacity-60"
                  style={{ background: "var(--app-accent)", color: "#fff" }}
                >
                  <FloppyDisk size={14} weight="duotone" />
                  Save
                </button>
                <button
                  onClick={remove}
                  disabled={busy}
                  aria-label={`Remove ${selected.part}`}
                  className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px] disabled:opacity-60"
                  style={{ border: "1px solid var(--app-neg-line)", color: "var(--app-neg)" }}
                >
                  <Trash size={14} weight="duotone" />
                </button>
              </div>
            )}
          </div>
        )}
      </aside>
    </main>
  );
}
