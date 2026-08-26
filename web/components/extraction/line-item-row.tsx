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
  const [draft, setDraft] = useState<Record<string, string>>(() => ({
    mark: item.mark ?? "",
    description: item.description ?? "",
    size: item.size ?? "",
    qty: String(item.qty ?? 1),
    division: item.division ?? "",
    hwSet: item.hwSet ?? "",
  }));

  const status = STATUS[item.status];
  const evidence = item.evidence;

  async function call(path: string, init: RequestInit, success: string) {
    setBusy(true);
    const response = await fetch(`/api/proxy/projects/${code}/line-items${path}`, init);
    setBusy(false);

    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      toast.error("That did not go through", { description: String(body.detail) });
      return false;
    }
    toast.success(success);
    onChanged();
    return true;
  }

  const confirm = () =>
    call(`/${item.id}/confirm`, { method: "POST" }, `${item.mark ?? "Line"} kept as is`);

  const save = () =>
    call(
      `/${item.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mark: draft.mark || null,
          description: draft.description,
          size: draft.size || null,
          qty: Number(draft.qty) || 1,
          division: draft.division || null,
          hwSet: draft.hwSet || null,
        }),
      },
      "Your changes are saved",
    );

  const remove = () =>
    call(`/${item.id}`, { method: "DELETE" }, `${item.mark ?? "Line"} removed`);

  const resolveDuplicate = (keep: "one" | "both") =>
    call(
      `/${item.id}/resolve-duplicate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keep }),
      },
      keep === "one" ? "Kept one reading" : "Kept both as separate lines",
    );

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
        className="grid cursor-pointer items-center gap-3 px-4 py-2.5"
        style={{ gridTemplateColumns: "28px 34px 60px 1fr 110px 60px 100px 120px" }}
        onClick={() => {
          const next = !open;
          setOpen(next);
          onSelect(next ? item : null);
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
                <span
                  key={flag}
                  className="rounded px-1.5 text-[10px]"
                  style={{ background: "var(--app-warn-soft)", color: "var(--app-warn)" }}
                >
                  {flag.replace(/_/g, " ")}
                </span>
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
              className="mt-3.5 grid gap-2.5"
              style={{ gridTemplateColumns: EDITABLE.map((f) => f.width).join(" ") }}
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
                    onChange={(event) =>
                      setDraft((current) => ({ ...current, [field.key]: event.target.value }))
                    }
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
                disabled={busy}
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
