"use client";

import { Checks, Trash } from "@phosphor-icons/react/dist/ssr";

export function BulkBar({
  selected,
  total,
  busy,
  onSelectAll,
  onConfirm,
  onRemove,
  onClear,
}: {
  selected: number;
  total: number;
  busy: boolean;
  onSelectAll: () => void;
  onConfirm: () => void;
  onRemove: () => void;
  onClear: () => void;
}) {
  if (selected === 0) return null;

  return (
    <div
      className="anim-fadein flex items-center gap-2 border-t px-4 py-2.5"
      style={{ borderColor: "var(--app-line)", background: "var(--app-accent-soft)" }}
    >
      <span className="text-[12.5px] font-semibold" style={{ color: "var(--app-accent)" }}>
        {selected} selected
      </span>
      <button
        onClick={onSelectAll}
        className="text-[12px] underline-offset-2 hover:underline"
        style={{ color: "var(--app-tx-2)" }}
      >
        Select all {total}
      </button>

      <span className="flex-1" />

      <button
        onClick={onConfirm}
        disabled={busy}
        className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-semibold disabled:opacity-50"
        style={{ background: "var(--app-accent)", color: "#fff" }}
      >
        <Checks size={13} weight="duotone" />
        Confirm {selected}
      </button>
      <button
        onClick={onRemove}
        disabled={busy}
        className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] disabled:opacity-50"
        style={{ border: "1px solid var(--app-neg-line)", color: "var(--app-neg)" }}
      >
        <Trash size={13} weight="duotone" />
        Remove
      </button>
      <button
        onClick={onClear}
        className="rounded-md px-3 py-1.5 text-[12px]"
        style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
      >
        Clear
      </button>
    </div>
  );
}
