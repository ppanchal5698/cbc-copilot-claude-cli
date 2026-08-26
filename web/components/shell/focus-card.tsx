"use client";

import { useUiState } from "@/components/shell/ui-state";

/**
 * The rail's bottom card.
 *
 * Focus mode quiets the run pill and the notification badge so a long review
 * pass is not interrupted by a job finishing. It hides nothing that would let a
 * flagged line slip through - the counts on the extraction screen stay put.
 */
export function FocusCard({ user }: { user: { name: string; email: string; initials: string } }) {
  const { focusMode, toggleFocus } = useUiState();

  return (
    <div
      className="m-3 rounded-xl p-3"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="flex items-center gap-2.5">
        <span
          className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-[11.5px] font-semibold"
          style={{ background: "var(--app-accent-soft)", color: "var(--app-accent)" }}
        >
          {user.initials}
        </span>
        <span className="flex min-w-0 flex-col leading-tight">
          <span className="truncate text-[12.5px] font-semibold">{user.name}</span>
          <span className="truncate text-[10.5px]" style={{ color: "var(--app-tx-3)" }}>
            {user.email}
          </span>
        </span>
      </div>

      <div className="mt-3 flex items-center justify-between">
        <span className="text-[12px]">Focus mode</span>
        <button
          onClick={toggleFocus}
          role="switch"
          aria-checked={focusMode}
          aria-label="Focus mode"
          className="relative h-[18px] w-[32px] rounded-full transition-colors"
          style={{ background: focusMode ? "var(--app-accent)" : "var(--app-panel-2)" }}
        >
          <span
            className="absolute top-[2px] h-[14px] w-[14px] rounded-full transition-all"
            style={{ left: focusMode ? 16 : 2, background: "#fff" }}
          />
        </button>
      </div>

      <p className="mt-1.5 text-[10.5px]" style={{ color: "var(--app-tx-3)" }}>
        {focusMode
          ? "Run status and notifications are quiet."
          : "Quiets run status and notifications."}
      </p>
    </div>
  );
}
