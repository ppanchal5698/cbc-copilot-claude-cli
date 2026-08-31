"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MagnifyingGlass, X } from "@phosphor-icons/react/dist/ssr";

import { useDebounced } from "@/hooks/use-debounced";

/** Debounced bid board search wired to the `?q=` URL param. */
export function BidBoardSearch({
  stage,
  initialQuery = "",
}: {
  stage?: string;
  initialQuery?: string;
}) {
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const settled = useDebounced(query.trim());

  useEffect(() => {
    if (settled === initialQuery.trim()) return;

    const params = new URLSearchParams();
    if (stage && stage !== "all") params.set("stage", stage);
    if (settled) params.set("q", settled);

    const qs = params.toString();
    router.replace(qs ? `/bids?${qs}` : "/bids");
  }, [settled, initialQuery, router, stage]);

  return (
    <div
      className="relative flex h-9 w-full max-w-sm items-center gap-2 rounded-lg px-3"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <MagnifyingGlass size={15} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search bids by code, name, brand…"
        aria-label="Search bids"
        className="min-w-0 flex-1 bg-transparent text-[13px] outline-none"
        style={{ color: "var(--app-tx)" }}
      />
      {query && (
        <button
          type="button"
          onClick={() => setQuery("")}
          aria-label="Clear search"
          className="rounded p-0.5"
          style={{ color: "var(--app-tx-3)" }}
        >
          <X size={14} weight="bold" />
        </button>
      )}
    </div>
  );
}
