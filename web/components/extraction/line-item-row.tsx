"use client";

import { useState } from "react";
import {
  CheckCircle,
  Copy,
  WarningCircle,
  PencilSimple,
  Trash,
  FloppyDisk,
  Eye,
} from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { StatusBadge } from "@/components/ui/status-badge";
import { errorMessage, proxyMutate } from "@/lib/proxy-fetcher";
import type { LineItem, LineStatus } from "@/lib/types";

const STATUS: Record<
  LineStatus,
  { label: string; colour: string; soft: string; line: string; Icon: typeof CheckCircle }
> = {
  clear: {
    label: "Clear",
    colour: "var(--app-accent)",
    soft: "var(--app-accent-soft)",
    line: "var(--app-accent-line)",
    Icon: CheckCircle,
  },
  needs_look: {
    label: "Looks right",
    colour: "var(--app-warn)",
    soft: "var(--app-warn-soft)",
    line: "var(--app-warn-line)",
    Icon: WarningCircle,
  },
  duplicate: {
    label: "Keep one",
    colour: "var(--app-neg)",
    soft: "var(--app-neg-soft)",
    line: "var(--app-neg-line)",
    Icon: Copy,
  },
  by_hand: {
    label: "By hand",
    colour: "var(--app-pos)",
    soft: "var(--app-pos-soft)",
    line: "var(--app-pos)",
    Icon: PencilSimple,
  },
};

/** Must match the header in ExtractionClient, hence the shared constant. */
export const ROW_COLUMNS = "28px 34px 60px minmax(160px,1fr) 110px 60px 100px 120px";

const EDITABLE = [
  { key: "mark", label: "Mark", width: "80px" },
  { key: "description", label: "Description", width: "1fr" },
  { key: "size", label: "Size", width: "110px" },
  { key: "qty", label: "Qty", width: "70px" },
  { key: "division", label: "Division", width: "110px" },
  { key: "hwSet", label: "HW set", width: "110px" },
] as const;

export function LineItemRow({
  item,
  code,
  selected,
  focused = false,
  picked = false,
  onPick,
  onSelect,
  onChanged,
}: {
  item: LineItem;
  code: string;
  selected: boolean;
  /** The keyboard cursor is on this row. */
  focused?: boolean;
  /** Ticked for a bulk action. */
  picked?: boolean;
  onPick?: () => void;
  onSelect: (item: LineItem | null) => void;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [edits, setEdits] = useState<{ from: string; values: Record<string, string> } | null>(
    null,
  );

  const status = STATUS[item.status];
  const evidence = item.evidence;

  // Identity of the server's version of this row. The draft used to be seeded
  // once and never re-synced, so a re-run that changed a line while the screen
  // was open left the form showing the old values - and "Save my changes" wrote
  // them straight back over what Claude had just read.
  const revision = [
    item.mark,
    item.description,
    item.size,
    item.qty,
    item.division,
    item.hwSet,
    item.confirmedAt,
  ].join("\u0000");

  const draft =
    edits?.from === revision
      ? edits.values
      : {
          mark: item.mark ?? "",
          description: item.description ?? "",
          size: item.size ?? "",
          qty: String(item.qty ?? 1),
          division: item.division ?? "",
          hwSet: item.hwSet ?? "",
        };

  const dirty = edits?.from === revision;

  function setField(key: string, value: string) {
    setEdits({ from: revision, values: { ...draft, [key]: value } });
  }

  async function call(
    path: string,
    init: Parameters<typeof proxyMutate>[1],
    success: string,
  ): Promise<boolean> {
    setBusy(true);
    try {
      await proxyMutate(`/api/proxy/projects/${code}/line-items${path}`, init);
      toast.success(success);
      setEdits(null);
      onChanged();
      return true;
    } catch (problem) {
      toast.error("That did not go through", { description: errorMessage(problem) });
      return false;
    } finally {
      setBusy(false);
    }
  }

  const confirm = () =>
    call(`/${item.id}/confirm`, { method: "POST" }, `${item.mark ?? "Line"} kept as is`);

  const save = () => {
    const qty = Number(draft.qty);
    if (draft.qty.trim() === "" || Number.isNaN(qty) || qty <= 0) {
      toast.error("Quantity has to be a positive number", {
        description: `"${draft.qty}" is not one, so nothing was saved.`,
      });
      return Promise.resolve(false);
    }
    if (!draft.description.trim()) {
      toast.error("A line needs a description");
      return Promise.resolve(false);
    }
    return call(
      `/${item.id}`,
      {
        method: "PATCH",
        body: {
          mark: draft.mark || null,
          description: draft.description.trim(),
          size: draft.size || null,
          qty,
          division: draft.division || null,
          hwSet: draft.hwSet || null,
        },
      },
      "Your changes are saved",
    );
  };

  const remove = () => {
    if (!window.confirm(`Remove ${item.mark ?? "this line"} — "${item.description}"?`)) {
      return Promise.resolve(false);
    }
    return call(`/${item.id}`, { method: "DELETE" }, `${item.mark ?? "Line"} removed`);
  };

  const resolveDuplicate = (keep: "one" | "both") =>
    call(
      `/${item.id}/resolve-duplicate`,
      { method: "POST", body: { keep } },
      keep === "one" ? "Kept one reading" : "Kept both as separate lines",
    );

  function toggleOpen() {
    const next = !open;
    setOpen(next);
    onSelect(next ? item : null);
  }

  return (
    <div
      data-row-id={item.id}
      className="border-b"
      style={{
        borderColor: "var(--app-line)",
        background: picked
          ? "var(--app-accent-soft)"
          : selected
            ? "var(--app-panel-2)"
            : "transparent",
        boxShadow: focused ? "inset 3px 0 0 var(--app-accent)" : undefined,
      }}
    >
      <div
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-label={`${item.mark ? `${item.mark}: ` : ""}${item.description}`}
        className="grid cursor-pointer items-center gap-3 px-4 py-2.5"
        style={{ gridTemplateColumns: ROW_COLUMNS }}
        onClick={toggleOpen}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            toggleOpen();
          }
        }}
      >
        <span onClick={(event) => event.stopPropagation()}>
          <input
            type="checkbox"
            aria-label={`Select ${item.mark ?? item.description}`}
            checked={picked}
            onChange={() => onPick?.()}
          />
        </span>

        <span
          className="grid h-6 w-6 place-items-center rounded-md"
          style={{ background: status.soft, color: status.colour }}
        >
          <status.Icon size={14} weight="duotone" />
        </span>

        <span className="tnum text-[13px] font-semibold">{item.mark ?? "—"}</span>

        <span className="min-w-0">
          <span className="block truncate text-[13px]">{item.description}</span>
          {item.flags.length > 0 && (
            <span className="mt-0.5 flex flex-wrap gap-1">
              {item.flags.slice(0, 3).map((flag) => (
                <StatusBadge key={flag} variant="caution" dashed>
                  {flag.replace(/_/g, " ")}
                </StatusBadge>
              ))}
            </span>
          )}
        </span>

        <span className="tnum text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
          {item.size ?? "—"}
        </span>
        <span className="tnum text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
          {item.qty}
        </span>
        <span className="text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
          {item.hwSet ?? "—"}
        </span>

        <span className="flex justify-end">
          <span
            className="rounded-md px-2.5 py-1 text-[11.5px] font-semibold"
            style={{
              background: status.soft,
              color: status.colour,
              border: `1px solid ${status.line}`,
            }}
          >
            {status.label}
          </span>
        </span>
      </div>

      {open && (
        <div className="anim-fadein px-4 pb-4">
          <div
            className="rounded-lg p-4"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            <div className="flex items-start gap-2.5">
              <status.Icon size={16} weight="duotone" style={{ color: status.colour }} />
              <div className="min-w-0 flex-1">
                <span className="block text-[13px] font-semibold">
                  {item.addedByHand
                    ? "Added by hand"
                    : item.status === "duplicate"
                      ? "Read twice"
                      : item.confidence && item.confidence >= 0.75
                        ? "Read cleanly from the sheet"
                        : "Worth a second look"}
                </span>
                <span className="mt-0.5 block text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                  {evidence?.note ??
                    (item.addedByHand
                      ? "Typed in by an estimator, so there is nothing to check it against."
                      : "Read from the door schedule.")}
                </span>
                <span className="mt-1 block text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                  {evidence?.sourcePage ? `page ${evidence.sourcePage}` : "no source page"}
                  {evidence?.row ? ` · row ${evidence.row}` : ""}
                  {item.confidence !== null && item.confidence !== undefined
                    ? ` · ${Math.round(item.confidence * 100)}% confidence`
                    : ""}
                  {!evidence?.bbox && !item.addedByHand && " · no position recorded"}
                </span>
              </div>

              {evidence?.sourcePage && (
                <button
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(item);
                  }}
                  className="flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11.5px]"
                  style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
                >
                  <Eye size={13} weight="duotone" />
                  See it on the sheet
                </button>
              )}
            </div>

            {item.status === "duplicate" && (
              <div
                className="mt-3 flex items-center gap-3 rounded-lg px-3 py-2.5"
                style={{
                  background: "var(--app-neg-soft)",
                  border: "1px solid var(--app-neg-line)",
                }}
              >
                <Copy size={15} weight="duotone" style={{ color: "var(--app-neg)" }} />
                <span className="flex-1 text-[12px]" style={{ color: "var(--app-neg)" }}>
                  {item.duplicateReason ?? "This line was read from more than one document."}
                </span>
                <button
                  onClick={() => resolveDuplicate("one")}
                  disabled={busy}
                  className="rounded-md px-2.5 py-1 text-[11.5px] font-semibold"
                  style={{ background: "var(--app-neg)", color: "#fff" }}
                >
                  Keep one
                </button>
                <button
                  onClick={() => resolveDuplicate("both")}
                  disabled={busy}
                  className="rounded-md px-2.5 py-1 text-[11.5px]"
                  style={{ border: "1px solid var(--app-neg-line)", color: "var(--app-neg)" }}
                >
                  Keep both
                </button>
              </div>
            )}

            <div
              className="mt-3.5 grid gap-2.5 sm:grid-cols-2 lg:[grid-template-columns:var(--editable-cols)]"
              style={
                {
                  "--editable-cols": EDITABLE.map((f) => f.width).join(" "),
                } as React.CSSProperties
              }
            >
              {EDITABLE.map((field) => (
                <label key={field.key} className="block">
                  <span
                    className="block text-[10.5px] uppercase tracking-[0.06em]"
                    style={{ color: "var(--app-tx-3)" }}
                  >
                    {field.label}
                  </span>
                  <input
                    value={draft[field.key] ?? ""}
                    inputMode={field.key === "qty" ? "numeric" : undefined}
                    onChange={(event) => setField(field.key, event.target.value)}
                    className="mt-1 w-full rounded-md px-2 py-1.5 text-[12.5px] outline-none focus:ring-2"
                    style={{
                      background: "var(--app-panel-2)",
                      border: "1px solid var(--app-line)",
                      color: "var(--app-tx)",
                    }}
                  />
                </label>
              ))}
            </div>

            <div className="mt-4 flex items-center gap-2">
              <button
                onClick={confirm}
                disabled={busy}
                className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-semibold disabled:opacity-60"
                style={{ background: "var(--app-accent)", color: "#fff" }}
              >
                <CheckCircle size={14} weight="duotone" />
                Keep as is
              </button>
              <button
                onClick={save}
                disabled={busy || !dirty}
                title={dirty ? undefined : "Nothing changed yet"}
                className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] disabled:opacity-60"
                style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
              >
                <FloppyDisk size={14} weight="duotone" />
                Save my changes
              </button>
              <span className="flex-1" />
              <button
                onClick={remove}
                disabled={busy}
                className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] disabled:opacity-60"
                style={{ color: "var(--app-neg)" }}
              >
                <Trash size={14} weight="duotone" />
                Remove
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
