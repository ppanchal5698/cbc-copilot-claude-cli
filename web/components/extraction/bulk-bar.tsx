"use client";

import { useState } from "react";
import { Checks, Trash, ArrowsLeftRight } from "@phosphor-icons/react/dist/ssr";

export function BulkBar({
  selected,
  total,
  busy,
  alternates,
  onSelectAll,
  onConfirm,
  onRemove,
  onClear,
  onAssignAlternate,
}: {
  selected: number;
  total: number;
  busy: boolean;
  alternates?: { name: string | null; label: string }[];
  onSelectAll: () => void;
  onConfirm: () => void;
  onRemove: () => void;
  onClear: () => void;
  onAssignAlternate?: (alternate: string | null) => void;
}) {
  const [assignOpen, setAssignOpen] = useState(false);
  const groups = alternates ?? [];

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

      {onAssignAlternate && groups.length > 0 && (
        <div className="relative">
          <button
            onClick={() => setAssignOpen((open) => !open)}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] disabled:opacity-50"
            style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
          >
            <ArrowsLeftRight size={13} weight="duotone" />
            Move to group
          </button>
          {assignOpen && (
            <div
              className="absolute bottom-full right-0 z-20 mb-1 min-w-[160px] rounded-lg py-1 shadow-lg"
              style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
            >
              {groups.map((group) => (
                <button
                  key={group.label}
                  onClick={() => {
                    onAssignAlternate(group.name);
                    setAssignOpen(false);
                  }}
                  className="block w-full px-3 py-1.5 text-left text-[12px] hover:bg-[var(--app-panel-2)]"
                  style={{ color: "var(--app-tx)" }}
                >
                  {group.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

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
