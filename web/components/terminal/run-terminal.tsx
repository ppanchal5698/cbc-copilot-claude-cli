"use client";

import { useCallback, useEffect, useRef } from "react";
import type { Terminal } from "@xterm/xterm";

import { useJobRecording, type RecordingState } from "@/hooks/use-job-recording";

import { LogViewer } from "./log-viewer";

import "@xterm/xterm/css/xterm.css";

/**
 * The real Claude Code session — structured log viewer by default, xterm for raw.
 *
 * The worker runs the CLI and records every byte; this replays the stream-json
 * events as they happen. Structured mode renders agent text, tool calls, and
 * errors as readable UI; raw mode shows the untouched JSON lines in xterm.
 *
 * It is read-only. There is no path from this component back into the process.
 */
export function RunTerminal({
  jobId,
  status,
  onFinished,
  raw = false,
}: {
  jobId: string;
  status?: string;
  onFinished?: (status: string) => void;
  /** Show the CLI's event stream unfiltered, exactly as it arrived. */
  raw?: boolean;
}) {
  const rawWriter = useRef<((lines: string) => void) | null>(null);
  const rawBuffer = useRef("");
  const onRawChunk = useCallback((lines: string) => {
    if (rawWriter.current) {
      rawWriter.current(lines);
    } else {
      rawBuffer.current += lines;
    }
  }, []);

  const { entries, state, reason } = useJobRecording(jobId, {
    onFinished,
    onRawChunk: raw ? onRawChunk : undefined,
    parseEntries: !raw,
  });

  return (
    <div className="flex h-full flex-col">
      <StatusStrip state={state} status={status} reason={reason} raw={raw} />
      <div className="min-h-0 flex-1" style={{ background: "var(--app-bg-2)" }}>
        {raw ? (
          state === "unavailable" ? (
            <div className="px-3 py-4 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
              {reason ?? "No recording available for this job."}
            </div>
          ) : (
            <RawXtermViewer
              registerWriter={(writer) => {
                rawWriter.current = writer;
                if (rawBuffer.current) {
                  writer(rawBuffer.current);
                  rawBuffer.current = "";
                }
              }}
            />
          )
        ) : state === "unavailable" ? (
          <div className="px-3 py-4 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
            {reason ?? "No recording available for this job."}
          </div>
        ) : (
          <LogViewer entries={entries} state={state} />
        )}
      </div>
    </div>
  );
}

function StatusStrip({
  state,
  status,
  reason,
  raw,
}: {
  state: RecordingState;
  status?: string;
  reason: string | null;
  raw: boolean;
}) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 text-[11px]"
      style={{ borderBottom: "1px solid var(--app-line)", color: "var(--app-tx-3)" }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{
          background:
            state === "live"
              ? "var(--app-accent)"
              : state === "ended"
                ? "var(--app-tx-3)"
                : "var(--app-warn)",
        }}
      />
      <span>
        {raw
          ? state === "live"
            ? "claude · raw json · live"
            : state === "ended"
              ? `claude · raw · ${status ?? "finished"}`
              : state === "unavailable"
                ? (reason ?? "no recording")
                : "connecting…"
          : state === "live"
            ? "claude · structured · live"
            : state === "ended"
              ? `claude · ${status ?? "finished"}`
              : state === "unavailable"
                ? (reason ?? "no recording")
                : "connecting…"}
      </span>
      <span className="flex-1" />
      <span>read-only</span>
    </div>
  );
}

function RawXtermViewer({
  registerWriter,
}: {
  registerWriter: (writer: (lines: string) => void) => void;
}) {
  const holder = useRef<HTMLDivElement | null>(null);
  const term = useRef<Terminal | null>(null);
  const pending = useRef("");

  useEffect(() => {
    let disposed = false;
    let fit: { fit: () => void; dispose: () => void } | null = null;
    let observer: ResizeObserver | null = null;

    registerWriter((lines) => {
      if (term.current) {
        term.current.write(lines);
      } else {
        pending.current += lines;
      }
    });

    (async () => {
      const [{ Terminal: XTerm }, { FitAddon }] = await Promise.all([
        import("@xterm/xterm"),
        import("@xterm/addon-fit"),
      ]);
      if (disposed || !holder.current) return;

      const styles = getComputedStyle(document.documentElement);
      const token = (name: string, fallback: string) =>
        styles.getPropertyValue(name).trim() || fallback;

      const terminal = new XTerm({
        convertEol: false,
        cursorBlink: false,
        disableStdin: true,
        scrollback: 20000,
        fontSize: 12,
        fontFamily:
          "var(--font-mono, ui-monospace), SFMono-Regular, Menlo, Consolas, monospace",
        theme: {
          background: token("--app-bg-2", "#0b0d10"),
          foreground: token("--app-tx", "#d8dde5"),
          cursor: token("--app-accent", "#7aa2f7"),
          selectionBackground: token("--app-accent-soft", "#24314d"),
        },
      });
      const fitAddon = new FitAddon();
      terminal.loadAddon(fitAddon);
      terminal.open(holder.current);
      fitAddon.fit();
      term.current = terminal;
      if (pending.current) {
        terminal.write(pending.current);
        pending.current = "";
      }
      fit = fitAddon;

      observer = new ResizeObserver(() => {
        try {
          fitAddon.fit();
        } catch {
          /* the pane can be measured mid-layout; the next tick fixes it */
        }
      });
      observer.observe(holder.current);
    })();

    return () => {
      disposed = true;
      registerWriter(() => {});
      observer?.disconnect();
      fit?.dispose();
      term.current?.dispose();
      term.current = null;
    };
  }, [registerWriter]);

  return <div ref={holder} className="h-full min-h-0 px-2 py-1.5" />;
}
