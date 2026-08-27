"use client";

import { useEffect, useRef, useState } from "react";
import type { Terminal } from "@xterm/xterm";

import { renderStream } from "@/lib/claude-stream";

import "@xterm/xterm/css/xterm.css";

/**
 * The real Claude Code session, rendered by a real terminal emulator.
 *
 * The worker runs the CLI on a pty and records every byte it writes; this
 * replays those bytes through xterm.js.
 *
 * `--print` on a pty turns out to emit only the final answer — a whole
 * extraction produced 14 bytes — so there is nothing to watch during the minutes
 * that matter. The run therefore uses `--output-format stream-json --verbose`,
 * where the CLI reports each tool call as it makes it, and every line below is
 * one of those events. The mapping is one-to-one with something the process
 * actually did; nothing is inferred, and `raw` shows the untouched stream.
 *
 * The interactive TUI would be more faithful still, but it stops on the
 * login-method screen and cannot be driven unattended.
 *
 * It is read-only. There is no path from this component back into the process,
 * because a browser that can type into a `--dangerously-skip-permissions`
 * session is a considerably worse idea than a browser that can only watch.
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
  const holder = useRef<HTMLDivElement | null>(null);
  const term = useRef<Terminal | null>(null);
  const offset = useRef(0);
  const carried = useRef("");
  const [state, setState] = useState<"connecting" | "live" | "ended" | "unavailable">(
    "connecting",
  );
  const [reason, setReason] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let source: EventSource | null = null;
    let fit: { fit: () => void; dispose: () => void } | null = null;
    let observer: ResizeObserver | null = null;

    // xterm touches `window` and `document` on construction, so it can only be
    // loaded in the browser.
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
      fit = fitAddon;

      observer = new ResizeObserver(() => {
        try {
          fitAddon.fit();
        } catch {
          /* the pane can be measured mid-layout; the next tick fixes it */
        }
      });
      observer.observe(holder.current);

      // Whatever already happened, before subscribing to what happens next.
      const replay = await fetch(`/api/proxy/jobs/${jobId}/terminal`).then((r) => r.json());
      if (disposed) return;

      if (!replay.available) {
        setState("unavailable");
        setReason(replay.reason ?? null);
      } else if (replay.data) {
        const first = renderStream(decode(replay.data), "", raw);
        terminal.write(first.lines);
        carried.current = first.remainder;
        offset.current = replay.bytes ?? 0;
      }

      if (replay.status && ["done", "failed", "cancelled"].includes(replay.status)) {
        setState("ended");
        return;
      }

      source = new EventSource(
        `/api/proxy/jobs/${jobId}/terminal/stream?offset=${offset.current}`,
      );
      setState("live");

      source.addEventListener("output", (event) => {
        const chunk = decode((event as MessageEvent).data);
        offset.current += chunk.length;
        // An event can arrive split across two reads, so the tail is carried.
        const next = renderStream(chunk, carried.current, raw);
        carried.current = next.remainder;
        if (next.lines) terminal.write(next.lines);
      });
      source.addEventListener("end", (event) => {
        setState("ended");
        source?.close();
        onFinished?.((event as MessageEvent).data);
      });
      source.onerror = () => {
        // The browser reconnects on its own; only a finished run closes it.
        if (source?.readyState === EventSource.CLOSED) setState("ended");
      };
    })();

    return () => {
      disposed = true;
      source?.close();
      observer?.disconnect();
      fit?.dispose();
      term.current?.dispose();
      term.current = null;
    };
  }, [jobId, raw]);

  return (
    <div className="flex h-full flex-col">
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
          {state === "live"
            ? "claude · stream-json · live"
            : state === "ended"
              ? `claude · ${status ?? "finished"}`
              : state === "unavailable"
                ? (reason ?? "no recording")
                : "connecting…"}
        </span>
        <span className="flex-1" />
        <span>read-only</span>
      </div>
      <div
        ref={holder}
        className="min-h-0 flex-1 px-2 py-1.5"
        style={{ background: "var(--app-bg-2)" }}
      />
    </div>
  );
}

/** The API base64s the recording so escape sequences survive JSON intact. */
function decode(payload: string): string {
  try {
    const binary = atob(payload);
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return payload;
  }
}
