"use client";

import { useState } from "react";
import useSWR from "swr";
import { Plus } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import type { LineItem, Product, Project } from "@/lib/types";

import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";

/**
 * Put a catalog part straight onto an open bid.
 *
 * The other direction of the extraction screen's composer: there, you search the
 * catalog from the bid; here, you pick the bid from the catalog. Both land the
 * same way - a by-hand line, already confirmed, because a human chose it.
 */
export function AddToBid({ product }: { product: Product }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const { data } = useSWR<{ projects: Project[] }>(
    open ? "/api/proxy/projects?limit=50" : null,
    proxyFetcher,
  );

  // A finished bid is the wrong place to drop a new line.
  const candidates = (data?.projects ?? []).filter((p) => p.stage !== "proposal");

  async function add(project: Project) {
    setBusy(true);
    try {
      await proxyMutate<LineItem>(`/api/proxy/projects/${project.code}/line-items`, {
        body: {
          description: product.description,
          part: product.part,
          division: product.division,
          qty: 1,
        },
      });
      toast.success(`${product.part} added to ${project.code}`, {
        description: "Marked as added by hand, and already confirmed.",
      });
      setOpen(false);
    } catch (problem) {
      toast.error("Could not add it", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-md py-2 text-[12.5px] font-semibold"
        style={{ background: "var(--app-accent-soft)", color: "var(--app-accent)", border: "1px solid var(--app-accent-line)" }}
      >
        <Plus size={14} weight="bold" />
        Add to a bid by hand
      </button>
    );
  }

  return (
    <div
      className="anim-fadein mt-4 rounded-lg p-3"
      style={{ background: "var(--app-panel-2)", border: "1px solid var(--app-line)" }}
    >
      <span className="block text-[11px] uppercase tracking-[0.07em]" style={{ color: "var(--app-tx-3)" }}>
        Add to which bid?
      </span>

      {!data ? (
        <p className="mt-2 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Loading bids…
        </p>
      ) : candidates.length === 0 ? (
        <p className="mt-2 text-[12px]" style={{ color: "var(--app-tx-2)" }}>
          No open bids to add to. Bids at the proposal stage are excluded.
        </p>
      ) : (
        <div className="mt-2 flex flex-col gap-1">
          {candidates.map((project) => (
            <button
              key={project.id}
              onClick={() => add(project)}
              disabled={busy}
              className="flex items-center gap-2 rounded-md px-2.5 py-2 text-left text-[12.5px] disabled:opacity-50 hover:bg-[var(--app-panel)]"
            >
              <span className="tnum font-semibold" style={{ color: "var(--app-accent)" }}>
                {project.code}
              </span>
              <span className="min-w-0 flex-1 truncate" style={{ color: "var(--app-tx-2)" }}>
                {project.name}
              </span>
              <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                {project.stage}
              </span>
            </button>
          ))}
        </div>
      )}

      <button
        onClick={() => setOpen(false)}
        className="mt-2 w-full rounded-md py-1.5 text-[12px]"
        style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
      >
        Cancel
      </button>
    </div>
  );
}
