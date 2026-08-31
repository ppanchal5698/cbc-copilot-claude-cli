import type { ReactNode } from "react";

const VARIANTS = {
  action: {
    color: "var(--app-accent)",
    background: "var(--app-accent-soft)",
    border: "var(--app-accent-line)",
  },
  review: {
    color: "var(--app-neg)",
    background: "var(--app-neg-soft)",
    border: "var(--app-neg-line)",
  },
  progress: {
    color: "var(--app-warn)",
    background: "var(--app-warn-soft)",
    border: "var(--app-warn-line)",
  },
  ok: {
    color: "var(--app-pos)",
    background: "var(--app-pos-soft)",
    border: "1px solid transparent",
  },
  caution: {
    color: "var(--app-warn)",
    background: "transparent",
    border: "var(--app-warn-line)",
  },
  neutral: {
    color: "var(--app-tx-3)",
    background: "var(--app-panel-2)",
    border: "1px solid transparent",
  },
} as const;

export type StatusBadgeVariant = keyof typeof VARIANTS;

export function StatusBadge({
  variant,
  children,
  className = "",
  dashed = false,
}: {
  variant: StatusBadgeVariant;
  children: ReactNode;
  className?: string;
  dashed?: boolean;
}) {
  const style = VARIANTS[variant];
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10.5px] font-semibold ${className}`}
      style={{
        color: style.color,
        background: style.background,
        border: dashed ? `1px dashed ${style.border}` : style.border,
      }}
    >
      {children}
    </span>
  );
}

export function statusBadgeVariantForQueueTag(tag: string): StatusBadgeVariant {
  if (tag.includes("Claude") || tag.includes("reading")) return "progress";
  if (tag.includes("to check")) return "review";
  if (tag.includes("Ready to hand off")) return "ok";
  if (tag.includes("Ready to price")) return "action";
  return "neutral";
}
