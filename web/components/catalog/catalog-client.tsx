"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Package, Plus, Trash, FloppyDisk, MagnifyingGlass } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { AddToBid } from "@/components/catalog/add-to-bid";
import { formatMoney } from "@/lib/api";
import type { Product } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

interface Response {
  products: Product[];
  total: number;
  divisions: { division: string; count: number }[];
}

const EDIT_FIELDS = [
  { key: "description", label: "Description", type: "text" },
  { key: "manufacturer", label: "Manufacturer", type: "text" },
  { key: "division", label: "Division", type: "text" },
  { key: "cost", label: "Our cost", type: "number" },
  { key: "listPrice", label: "List", type: "number" },
  { key: "multiplier", label: "Multiplier", type: "number" },
  { key: "availability", label: "Availability", type: "text" },
] as const;

export function CatalogClient() {
  const [query, setQuery] = useState("");
  const [division, setDivision] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState(false);

  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (division) params.set("division", division);

  const { data, mutate } = useSWR<Response>(
    `/api/proxy/catalog/products?${params.toString()}`,
    fetcher,
  );

  const products = data?.products ?? [];
  const selected = products.find((product) => product.id === selectedId) ?? null;

  useEffect(() => {
    if (!selected) return;
    setDraft({
      description: selected.description ?? "",
      manufacturer: selected.manufacturer ?? "",
      division: selected.division ?? "",
      cost: selected.cost === null ? "" : String(selected.cost),
      listPrice: selected.listPrice === null ? "" : String(selected.listPrice),
      multiplier: selected.multiplier === null ? "" : String(selected.multiplier),
      availability: selected.availability ?? "",
    });
  }, [selectedId, selected]);

  async function save() {
    if (!selected) return;
    const body: Record<string, unknown> = {};
    for (const field of EDIT_FIELDS) {
      const value = draft[field.key]?.trim() ?? "";
      body[field.key] = field.type === "number" ? (value === "" ? null : Number(value)) : value || null;
    }

    const response = await fetch(`/api/proxy/catalog/products/${selected.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      toast.error("Could not save that part");
      return;
    }
    toast.success(`${selected.part} saved`);
    mutate();
  }

  async function remove() {
    if (!selected) return;
    const response = await fetch(`/api/proxy/catalog/products/${selected.id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      toast.error("Could not remove that part");
      return;
    }
    toast.success(`${selected.part} removed`);
    setSelectedId(null);
    mutate();
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      part: String(form.get("part") ?? "").trim(),
      description: String(form.get("description") ?? "").trim(),
      manufacturer: String(form.get("manufacturer") ?? "").trim() || null,
      division: String(form.get("division") ?? "").trim() || null,
      cost: form.get("cost") ? Number(form.get("cost")) : null,
    };

    const response = await fetch("/api/proxy/catalog/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({ detail: response.statusText }));
      toast.error("Could not add that part", { description: String(detail.detail) });
      return;
    }
    toast.success(`${body.part} added to the catalog`);
    setCreating(false);
    mutate();
  }

  return (
    <main className="flex min-h-0 flex-1 gap-4 overflow-hidden p-4">
      <section className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-[20px] font-semibold">Product catalog</h1>
            <p className="mt-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
              {data?.total ?? 0} parts · maintained by Claude from the price books, editable here
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
            className="anim-fadein grid gap-2 rounded-xl p-3"
            style={{
              gridTemplateColumns: "170px 1fr 130px 110px 100px 90px",
              background: "var(--app-panel)",
              border: "1px solid var(--app-line)",
            }}
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
                step="0.01"
                required={field.required}
                placeholder={field.placeholder}
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
              className="rounded-md text-[12.5px] font-semibold"
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
            className="flex-1 bg-transparent text-[13px] outline-none"
            style={{ color: "var(--app-tx)" }}
          />
          <span className="tnum text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
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
                background: division === entry.division ? "var(--app-accent-soft)" : "var(--app-panel)",
                color: division === entry.division ? "var(--app-accent)" : "var(--app-tx-2)",
                border: `1px solid ${division === entry.division ? "var(--app-accent-line)" : "var(--app-line)"}`,
              }}
            >
              {entry.division} {entry.count}
            </button>
          ))}
        </div>

        <div
          className="min-h-0 flex-1 overflow-auto rounded-xl"
          style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
        >
          <div
            className="sticky top-0 grid gap-3 border-b px-4 py-2.5 text-[10.5px] uppercase tracking-[0.07em]"
            style={{
              gridTemplateColumns: "190px 1fr 130px 90px 100px 110px",
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

          {products.length === 0 ? (
            <div className="grid place-items-center px-6 py-16 text-center">
              <span className="text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
                No parts match. Upload a price book and Claude will fill the catalog in.
              </span>
            </div>
          ) : (
            products.map((product) => (
              <button
                key={product.id}
                onClick={() => setSelectedId(product.id)}
                className="grid w-full items-center gap-3 border-b px-4 py-2.5 text-left last:border-b-0"
                style={{
                  gridTemplateColumns: "190px 1fr 130px 90px 100px 110px",
                  borderColor: "var(--app-line)",
                  background:
                    selectedId === product.id ? "var(--app-panel-2)" : "transparent",
                  borderLeft:
                    selectedId === product.id
                      ? "3px solid var(--app-accent)"
                      : "3px solid transparent",
                }}
              >
                <span className="truncate text-[12.5px] font-semibold">{product.part}</span>
                <span className="truncate text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
                  {product.description}
                </span>
                <span className="truncate text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                  {product.manufacturer ?? "—"}
                </span>
                <span className="tnum text-right text-[12.5px]">
                  {product.cost === null ? "—" : `$${formatMoney(product.cost)}`}
                </span>
                <span className="tnum text-[12px]" style={{ color: "var(--app-tx-3)" }}>
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
      </section>

      <aside
        className="flex w-[330px] shrink-0 flex-col overflow-auto rounded-xl"
        style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
      >
        {!selected ? (
          <div className="grid flex-1 place-items-center gap-2 px-6 text-center">
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
                    step="0.001"
                    value={draft[field.key] ?? ""}
                    onChange={(event) =>
                      setDraft((current) => ({ ...current, [field.key]: event.target.value }))
                    }
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

            <div
              className="mt-4 flex items-baseline justify-between rounded-md px-3 py-2"
              style={{ background: "var(--app-panel-2)" }}
            >
              <span className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
                Sell at
              </span>
              <span className="tnum text-[14px] font-semibold" style={{ color: "var(--app-accent)" }}>
                {selected.sellAt === null ? "—" : `$${formatMoney(selected.sellAt)}`}
              </span>
            </div>
            <p className="mt-1.5 text-[11px]" style={{ color: "var(--app-tx-3)" }}>
              Sell follows the division&apos;s margin divisor. Overriding it on a quote line is
              logged against your name.
            </p>

            {selected.xref.length > 0 && (
              <div className="mt-4">
                <span
                  className="block text-[10.5px] uppercase tracking-[0.07em]"
                  style={{ color: "var(--app-tx-3)" }}
                >
                  Cross-reference
                </span>
                {selected.xref.map((entry) => (
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

            <div className="mt-5 flex gap-2">
              <button
                onClick={save}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-md py-2 text-[12.5px] font-semibold"
                style={{ background: "var(--app-accent)", color: "#fff" }}
              >
                <FloppyDisk size={14} weight="duotone" />
                Save
              </button>
              <button
                onClick={remove}
                className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px]"
                style={{ border: "1px solid var(--app-neg-line)", color: "var(--app-neg)" }}
              >
                <Trash size={14} weight="duotone" />
              </button>
            </div>
          </div>
        )}
      </aside>
    </main>
  );
}
