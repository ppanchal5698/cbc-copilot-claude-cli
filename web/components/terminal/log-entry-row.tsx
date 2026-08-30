"use client";

import { useState } from "react";
import { CaretDown, CaretRight, Warning } from "@phosphor-icons/react/dist/ssr";

import { AgentText } from "@/lib/format-agent-text";
import type { LogEntry } from "@/lib/claude-stream";

const PREVIEW_LIMIT = 2048;

function truncate(text: string, limit = PREVIEW_LIMIT): { text: string; truncated: boolean } {
  if (text.length <= limit) return { text, truncated: false };
  return { text: text.slice(0, limit), truncated: true };
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function StatusBadge({
  label,
  tone,
}: {
  label: string;
  tone: "ok" | "failed" | "neutral";
}) {
  const styles =
    tone === "ok"
      ? { background: "var(--app-pos-soft)", color: "var(--app-pos)" }
      : tone === "failed"
        ? { background: "var(--app-neg-soft)", color: "var(--app-neg)" }
        : { background: "var(--app-panel-2)", color: "var(--app-tx-3)" };

  return (
    <span className="rounded px-1.5 py-0.5 text-[10px] font-medium uppercase" style={styles}>
      {label}
    </span>
  );
}

function ToolCallRow({ entry }: { entry: Extract<LogEntry, { kind: "tool_call" }> }) {
  const [open, setOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const result = entry.result;
  const resultPreview = result ? truncate(result.body) : null;

  return (
    <div className="tool-card rounded-md" style={{ border: "1px solid var(--app-line)" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left"
        style={{ color: "var(--app-tx)" }}
      >
        {open ? <CaretDown size={12} /> : <CaretRight size={12} />}
        <span className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: "var(--app-accent)" }}>
          call
        </span>
        <span className="font-mono text-[12px]">{entry.name}</span>
        {entry.summary ? (
          <span className="truncate font-mono text-[11px]" style={{ color: "var(--app-tx-3)" }}>
            {entry.summary}
          </span>
        ) : null}
        <span className="flex-1" />
        {result ? (
          <>
            <StatusBadge label={result.isError ? "failed" : "ok"} tone={result.isError ? "failed" : "ok"} />
            <span className="font-mono text-[10px]" style={{ color: "var(--app-tx-3)" }}>
              {result.size.toLocaleString()} chars
            </span>
          </>
        ) : (
          <StatusBadge label="pending" tone="neutral" />
        )}
      </button>

      {open ? (
        <div
          className="space-y-2 px-2.5 pb-2.5"
          style={{ borderTop: "1px solid var(--app-line)" }}
        >
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase" style={{ color: "var(--app-tx-3)" }}>
              Input
            </div>
            <pre className="terminal-code-block">{formatJson(entry.input)}</pre>
          </div>
          {result ? (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase" style={{ color: "var(--app-tx-3)" }}>
                Result
              </div>
              <pre className="terminal-code-block">
                {showAll || !resultPreview?.truncated
                  ? result.body
                  : resultPreview.text}
              </pre>
              {resultPreview?.truncated ? (
                <button
                  type="button"
                  onClick={() => setShowAll((v) => !v)}
                  className="mt-1 text-[11px]"
                  style={{ color: "var(--app-accent)" }}
                >
                  {showAll ? "Show less" : "Show all"}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function LogEntryRow({ entry }: { entry: LogEntry }) {
  return (
    <div className="terminal-log-row grid grid-cols-[64px_1fr] gap-2 px-3 py-1.5">
      <time className="tnum pt-0.5 font-mono text-[10px]" style={{ color: "var(--app-tx-3)" }}>
        {entry.time}
      </time>

      <div className="min-w-0">
        {entry.kind === "session" ? (
          <div
            className="rounded-md px-2.5 py-2"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-semibold uppercase" style={{ color: "var(--app-accent)" }}>
                session
              </span>
              <span className="rounded px-1.5 py-0.5 font-mono text-[11px]" style={{ background: "var(--app-accent-soft)", color: "var(--app-accent)" }}>
                {entry.model}
              </span>
              <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                {entry.toolCount} tools
              </span>
            </div>
            {entry.mcpServers.length > 0 ? (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {entry.mcpServers.map((server) => (
                  <span
                    key={`${server.name}-${server.status}`}
                    className="rounded px-1.5 py-0.5 font-mono text-[10px]"
                    style={{
                      background: "var(--app-panel-2)",
                      color: server.status === "connected" ? "var(--app-pos)" : "var(--app-tx-3)",
                      border: "1px solid var(--app-line)",
                    }}
                  >
                    {server.name}:{server.status}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {entry.kind === "warning" || entry.kind === "api_retry" ? (
          <div
            className="flex items-start gap-2 rounded-md px-2.5 py-2"
            style={{
              background: "var(--app-warn-soft)",
              border: "1px solid var(--app-warn-line)",
              color: "var(--app-warn)",
            }}
          >
            <Warning size={14} className="mt-0.5 shrink-0" />
            <div className="min-w-0 text-[12px]">
              {entry.kind === "api_retry"
                ? `API retry ${entry.attempt}/${entry.maxRetries}: ${entry.error}`
                : entry.message}
            </div>
          </div>
        ) : null}

        {entry.kind === "agent_text" ? (
          <div className="rounded-md px-2.5 py-2" style={{ background: "var(--app-panel)" }}>
            <AgentText text={entry.text} />
          </div>
        ) : null}

        {entry.kind === "tool_call" ? <ToolCallRow entry={entry} /> : null}

        {entry.kind === "error" ? (
          <div
            className="rounded-md border-l-2 px-2.5 py-2 text-[12px]"
            style={{
              borderColor: "var(--app-neg)",
              background: "var(--app-neg-soft)",
              color: "var(--app-neg)",
            }}
          >
            {entry.message}
          </div>
        ) : null}

        {entry.kind === "done" ? (
          <div
            className="flex flex-wrap items-center gap-2 rounded-md px-2.5 py-2 text-[12px]"
            style={{
              background: entry.isError ? "var(--app-neg-soft)" : "var(--app-pos-soft)",
              color: entry.isError ? "var(--app-neg)" : "var(--app-pos)",
              border: `1px solid ${entry.isError ? "var(--app-neg-line)" : "var(--app-line)"}`,
            }}
          >
            <span className="font-semibold uppercase">done</span>
            <span>
              {entry.turns} turns in {entry.seconds}s
            </span>
            {entry.costUsd != null ? <span>${entry.costUsd.toFixed(3)}</span> : null}
          </div>
        ) : null}

        {entry.kind === "rate_limit" ? (
          <div className="text-[12px]" style={{ color: "var(--app-warn)" }}>
            rate limit: {entry.subtype}
          </div>
        ) : null}

        {entry.kind === "plain" ? (
          <div className="font-mono text-[11px]" style={{ color: "var(--app-tx-3)" }}>
            {entry.text}
          </div>
        ) : null}
      </div>
    </div>
  );
}
