"use client";

import { useEffect, useRef, useState } from "react";
import { PlusCircle } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { formatMoney } from "@/lib/api";
import type { Product } from "@/lib/types";

/**
 * "Add anything the drawings do not carry."
 *
 * Searches the live catalog by part number, description, manufacturer or
 * division. A free-typed description is allowed too - not everything an
 * estimator needs to add exists in the catalog yet.
 */
export function PartComposer({ code, onAdded }: { code: string; onAdded: () => void }) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Product[]>([]);
  const [busy, setBusy] = useState(false);
  const [focused, setFocused] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (query.trim().length < 2) {
      setHits([]);
      return;
    }
    timer.current = setTimeout(async () => {
      const response = await fetch(
        `/api/proxy/catalog/products?q=${encodeURIComponent(query)}&limit=6`,
      );
      if (response.ok) setHits((await response.json()).products);
    }, 220);

    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [query]);

  async function add(product?: Product) {
    const description = product?.description ?? query.trim();
    if (!description) return;

    setBusy(true);
    const response = await fetch(`/api/proxy/projects/${code}/line-items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        description,
        part: product?.part,
        division: product?.division,
        qty: 1,
      }),
    });
    setBusy(false);

    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      toast.error("Could not add that line", { description: String(body.detail) });
      return;
    }

    toast.success(product ? `${product.part} added` : "Line added", {
      description: "Marked as added by hand, and already confirmed.",
    });
    setQuery("");
    setHits([]);
    onAdded();
  }

  return (
    <div className="relative">
      <div
        className="flex items-center gap-3 rounded-xl px-4 py-3"
        style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
      >
        <PlusCircle size={18} weight="duotone" style={{ color: "var(--app-neg)" }} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 160)}
          onKeyDown={(event) => {
            if (event.key === "Enter") add(hits[0]);
          }}
          placeholder="Add anything the drawings do not carry — search a part number or type a description"
          className="flex-1 bg-transparent text-[13px] outline-none"
          style={{ color: "var(--app-tx)" }}
        />
        <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
          ↵ add
        </span>
        <button
          onClick={() => add(hits[0])}
          disabled={busy || query.trim().length === 0}
          className="rounded-md px-3 py-1.5 text-[12px] font-semibold disabled:opacity-50"
          style={{ background: "var(--app-neg)", color: "#fff" }}
        >
          Add line
        </button>
      </div>

      {focused && hits.length > 0 && (
        <div
          className="anim-fadein absolute bottom-full left-0 right-0 z-20 mb-2 overflow-hidden rounded-xl"
          style={{
            background: "var(--app-panel)",
            border: "1px solid var(--app-line)",
            boxShadow: "var(--app-sh-2)",
          }}
        >
          {hits.map((product) => (
            <button
              key={product.id}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => add(product)}
              className="grid w-full items-center gap-3 border-b px-4 py-2.5 text-left last:border-b-0 hover:bg-[var(--app-panel-2)]"
              style={{ gridTemplateColumns: "170px 1fr 110px 90px", borderColor: "var(--app-line)" }}
            >
              <span className="truncate text-[12.5px] font-semibold" style={{ color: "var(--app-accent)" }}>
                {product.part}
              </span>
              <span className="truncate text-[12.5px]">{product.description}</span>
              <span className="truncate text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
                {product.manufacturer ?? "—"}
              </span>
              <span className="tnum text-right text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                {product.cost === null ? "manual" : `$${formatMoney(product.cost)}`}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
