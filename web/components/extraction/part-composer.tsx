"use client";

import { useEffect, useState } from "react";
import { PlusCircle } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { useDebounced } from "@/hooks/use-debounced";
import { formatMoney } from "@/lib/format";
import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import type { LineItem, Product, ProductSearchResponse } from "@/lib/types";

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

  const settled = useDebounced(query.trim());
  const tooShort = settled.length < 2;

  useEffect(() => {
    if (tooShort) return;

    // Aborting the superseded request is what stops a slow early response from
    // landing on top of a fast later one.
    const controller = new AbortController();
    (async () => {
      try {
        const found = await proxyFetcher<ProductSearchResponse>(
          `/api/proxy/catalog/products?q=${encodeURIComponent(settled)}&limit=6`,
          controller.signal,
        );
        setHits(found.products);
      } catch {
        /* aborted, or the search failed - the composer still accepts free text */
      }
    })();

    return () => controller.abort();
  }, [settled, tooShort]);

  // Derived rather than cleared in an effect, so a stale list is never rendered
  // for one frame after the query is emptied.
  const visible = tooShort ? [] : hits;

  async function add(product?: Product) {
    const description = product?.description ?? query.trim();
    if (!description) return;

    setBusy(true);
    try {
      await proxyMutate<LineItem>(`/api/proxy/projects/${code}/line-items`, {
        body: {
          description,
          part: product?.part,
          division: product?.division,
          qty: 1,
        },
      });
      toast.success(product ? `${product.part} added` : "Line added", {
        description: "Marked as added by hand, and already confirmed.",
      });
      setQuery("");
      setHits([]);
      onAdded();
    } catch (problem) {
      toast.error("Could not add that line", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
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
            if (event.key === "Enter") add();
          }}
          placeholder="Add anything the drawings do not carry — search a part number or type a description"
          aria-label="Add a line by hand"
          className="min-w-0 flex-1 bg-transparent text-[13px] outline-none"
          style={{ color: "var(--app-tx)" }}
        />
        <span className="hidden text-[11px] sm:inline" style={{ color: "var(--app-tx-3)" }}>
          ↵ add
        </span>
        <button
          onClick={() => add()}
          disabled={busy || query.trim().length === 0}
          className="shrink-0 rounded-md px-3 py-1.5 text-[12px] font-semibold disabled:opacity-50"
          style={{ background: "var(--app-neg)", color: "#fff" }}
        >
          Add line
        </button>
      </div>

      {focused && visible.length > 0 && (
        <div
          className="anim-fadein absolute bottom-full left-0 right-0 z-20 mb-2 overflow-hidden rounded-xl"
          style={{
            background: "var(--app-panel)",
            border: "1px solid var(--app-line)",
            boxShadow: "var(--app-sh-2)",
          }}
        >
          {visible.map((product) => (
            <button
              key={product.id}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => add(product)}
              className="grid w-full items-center gap-3 border-b px-4 py-2.5 text-left last:border-b-0 hover:bg-[var(--app-panel-2)]"
              style={{
                gridTemplateColumns: "minmax(120px,170px) 1fr 110px 90px",
                borderColor: "var(--app-line)",
              }}
            >
              <span
                className="truncate text-[12.5px] font-semibold"
                style={{ color: "var(--app-accent)" }}
              >
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
