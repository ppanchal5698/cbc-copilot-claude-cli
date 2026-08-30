"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  countByFilter,
  entryMatchesFilter,
  type LogEntry,
  type LogFilter,
} from "@/lib/claude-stream";
import type { RecordingState } from "@/hooks/use-job-recording";

import { LogEntryRow } from "./log-entry-row";

const FILTERS: { id: LogFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "agent", label: "Agent" },
  { id: "tools", label: "Tools" },
  { id: "system", label: "System" },
  { id: "errors", label: "Errors" },
];

export function LogViewer({
  entries,
  state,
}: {
  entries: LogEntry[];
  state: RecordingState;
}) {
  const [filter, setFilter] = useState<LogFilter>("all");
  const [pinnedBottom, setPinnedBottom] = useState(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const counts = useMemo(() => countByFilter(entries), [entries]);
  const visible = useMemo(
    () => entries.filter((entry) => entryMatchesFilter(entry, filter)),
    [entries, filter],
  );

  const isNearBottom = () => {
    const el = scrollRef.current;
    if (!el) return true;
    return el.scrollTop + el.clientHeight >= el.scrollHeight - 48;
  };

  useEffect(() => {
    if (!pinnedBottom) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [visible.length, pinnedBottom, state]);

  const onScroll = () => {
    setPinnedBottom(isNearBottom());
  };

  const jumpToBottom = () => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    setPinnedBottom(true);
  };

  return (
    <div className="terminal-log flex h-full min-h-0 flex-col">
      <div
        className="flex flex-wrap items-center gap-1 px-3 py-1.5"
        style={{ borderBottom: "1px solid var(--app-line)" }}
      >
        {FILTERS.map((chip) => {
          const on = filter === chip.id;
          const count = counts[chip.id];
          return (
            <button
              key={chip.id}
              type="button"
              onClick={() => setFilter(chip.id)}
              className="rounded px-2 py-0.5 text-[11px]"
              style={{
                background: on ? "var(--app-accent-soft)" : "transparent",
                border: `1px solid ${on ? "var(--app-accent-line)" : "var(--app-line)"}`,
                color: on ? "var(--app-accent)" : "var(--app-tx-3)",
              }}
            >
              {chip.label}
              {chip.id !== "all" && count > 0 ? ` (${count})` : ""}
            </button>
          );
        })}
        <span className="flex-1" />
        <span className="text-[10px]" style={{ color: "var(--app-tx-3)" }}>
          {visible.length} events
        </span>
      </div>

      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="terminal-log-scroll h-full overflow-y-auto py-1"
        >
          {visible.length === 0 ? (
            <div className="px-3 py-6 text-center text-[12px]" style={{ color: "var(--app-tx-3)" }}>
              {state === "connecting"
                ? "Connecting to run recording…"
                : "No events match this filter yet."}
            </div>
          ) : (
            visible.map((entry) => <LogEntryRow key={entry.id} entry={entry} />)
          )}
        </div>

        {!pinnedBottom && state === "live" ? (
          <button
            type="button"
            onClick={jumpToBottom}
            className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-1 text-[11px] shadow-app-2"
            style={{
              background: "var(--app-panel)",
              border: "1px solid var(--app-accent-line)",
              color: "var(--app-accent)",
            }}
          >
            ↓ New output
          </button>
        ) : null}
      </div>
    </div>
  );
}
