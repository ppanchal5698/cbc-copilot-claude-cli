import type { ReactNode } from "react";

export function StagePanel({
  icon,
  title,
  subtitle,
  actions,
}: {
  icon: ReactNode;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div
      className="flex flex-wrap items-start justify-between gap-3 rounded-xl px-4 py-3"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="flex min-w-0 items-start gap-3">
        <span
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg"
          style={{ background: "var(--app-accent-soft)", color: "var(--app-accent)" }}
        >
          {icon}
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="text-[15px] font-semibold">{title}</span>
          {subtitle ? (
            <span className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
              {subtitle}
            </span>
          ) : null}
        </span>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
