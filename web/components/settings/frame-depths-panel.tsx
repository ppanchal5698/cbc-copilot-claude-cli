"use client";

import { useState } from "react";
import useSWR from "swr";
import { Ruler, Plus, Trash } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import type { FrameDepths } from "@/lib/types";

const DEPTHS_URL = "/api/proxy/reference/frame-depths";

/**
 * Edit frame throat depths by wall type (Matrix 7.0). Read by the take-off pass
 * to derive a frame depth. `depth` is a label like 5-3/4; the API derives the
 * inches. Writes reference-library/frame_depths/wall_type_to_depth.json.
 */
export function FrameDepthsPanel() {
  const { data, error, isLoading, mutate } = useSWR<FrameDepths>(DEPTHS_URL, proxyFetcher);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({ type: "", depth: "" });

  async function save(body: Record<string, unknown>, success: string) {
    setBusy(true);
    try {
      await proxyMutate<FrameDepths>(DEPTHS_URL, { method: "PATCH", body });
      toast.success(success);
      mutate();
    } catch (problem) {
      toast.error("Could not save that depth", { description: errorMessage(problem) });
      mutate();
    } finally {
      setBusy(false);
    }
  }

  function commitDepth(type: string, raw: string, current: string) {
    const next = raw.trim();
    if (next === current.trim()) return;
    if (!next) {
      toast.error("Depth cannot be blank", { description: "e.g. 5-3/4 or 5.75." });
      mutate();
      return;
    }
    save({ wall_types: [{ type, depth: next }] }, `${type} set to ${next}"`);
  }

  function commitNote(type: string, raw: string, current: string) {
    if (raw.trim() === current.trim()) return;
    save({ wall_types: [{ type, note: raw.trim() || null }] }, `${type} note updated`);
  }

  function add(event: React.FormEvent) {
    event.preventDefault();
    const type = draft.type.trim();
    const depth = draft.depth.trim();
    if (!type) {
      toast.error("Give the wall type a name");
      return;
    }
    if (!depth) {
      toast.error("Enter a depth", { description: "e.g. 5-3/4 or 5.75." });
      return;
    }
    save({ wall_types: [{ type, depth }] }, `${type} added`);
    setDraft({ type: "", depth: "" });
  }

  function remove(type: string) {
    if (!window.confirm(`Remove the "${type}" wall type?`)) return;
    save({ remove: [type] }, `${type} removed`);
  }

  const inputStyle = {
    background: "var(--app-panel-2)",
    border: "1px solid var(--app-line)",
    color: "var(--app-tx)",
  };
  const wallTypes = data?.wall_types ?? [];

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <div className="flex items-center gap-2">
          <Ruler size={16} weight="duotone" style={{ color: "var(--app-accent)" }} />
          <h2 className="text-[15px] font-semibold">Frame depths by wall type</h2>
        </div>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Throat depth the take-off derives from wall construction. Enter as 5-3/4 or 5.75.
          Administrators only.
        </p>
      </div>

      {error && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-neg)" }}>
          Could not read the frame depths: {errorMessage(error)}
        </p>
      )}
      {isLoading && !data && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Loading…
        </p>
      )}

      {data && (
        <div className="divide-y" style={{ borderColor: "var(--app-line)" }}>
          {wallTypes.map((wall) => (
            <div key={wall.type} className="px-4 py-2.5" style={{ borderColor: "var(--app-line)" }}>
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium capitalize">
                  {wall.type}
                </span>
                <span className="tnum shrink-0 text-[11px]" style={{ color: "var(--app-tx-3)", width: "56px", textAlign: "right" }}>
                  {wall.depth_inches}&quot;
                </span>
                <input
                  key={`${wall.type}-${wall.depth}`}
                  defaultValue={wall.depth}
                  disabled={busy}
                  aria-label={`${wall.type} depth`}
                  onBlur={(event) => commitDepth(wall.type, event.target.value, wall.depth)}
                  className="tnum w-20 shrink-0 rounded-md px-2.5 py-1.5 text-right text-[12.5px] outline-none focus:ring-2"
                  style={inputStyle}
                />
                <button
                  type="button"
                  onClick={() => remove(wall.type)}
                  disabled={busy}
                  aria-label={`Remove ${wall.type}`}
                  className="shrink-0 rounded-md p-1.5"
                  style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-3)" }}
                >
                  <Trash size={14} />
                </button>
              </div>
              <input
                key={`${wall.type}-note-${wall.note ?? ""}`}
                defaultValue={wall.note ?? ""}
                disabled={busy}
                placeholder="note (optional)"
                aria-label={`${wall.type} note`}
                onBlur={(event) => commitNote(wall.type, event.target.value, wall.note ?? "")}
                className="mt-1.5 w-full rounded-md px-2.5 py-1 text-[11px] outline-none focus:ring-2"
                style={{ ...inputStyle, color: "var(--app-tx-2)" }}
              />
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
          <input
            value={draft.type}
            onChange={(event) => setDraft((d) => ({ ...d, type: event.target.value }))}
            placeholder="Wall type, e.g. masonry"
            aria-label="New wall type"
            className="min-w-0 flex-1 rounded-md px-2.5 py-1.5 text-[12.5px] outline-none focus:ring-2"
            style={inputStyle}
          />
          <input
            value={draft.depth}
            onChange={(event) => setDraft((d) => ({ ...d, depth: event.target.value }))}
            placeholder="5-3/4"
            aria-label="New wall type depth"
            className="tnum w-24 rounded-md px-2.5 py-1.5 text-right text-[12.5px] outline-none focus:ring-2"
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

      {data?.unknown_wall_type_rule && (
        <p
          className="border-t px-4 py-2.5 text-[11px]"
          style={{ borderColor: "var(--app-line)", color: "var(--app-tx-3)" }}
        >
          {data.unknown_wall_type_rule}
          {data.adjustable_frames ? " Adjustable frames are a valid answer when the wall type is unclear." : ""}
        </p>
      )}
    </section>
  );
}
