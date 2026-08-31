"use client";

import { useEffect, useRef, useState } from "react";

import {
  decodeBase64Recording,
  mergeEntries,
  parseStream,
  renderStream,
  type LogEntry,
} from "@/lib/claude-stream";
import { endpoints } from "@/lib/endpoints";
import { proxyFetch } from "@/lib/proxy-fetcher";

export type RecordingState = "connecting" | "live" | "ended" | "unavailable";

interface TerminalReplay {
  available: boolean;
  reason?: string | null;
  data?: string | null;
  bytes?: number | null;
  status?: string | null;
}

export function useJobRecording(
  jobId: string,
  options?: {
    onFinished?: (status: string) => void;
    onRawChunk?: (lines: string) => void;
    parseEntries?: boolean;
  },
) {
  const { onFinished, onRawChunk, parseEntries = true } = options ?? {};
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [state, setState] = useState<RecordingState>("connecting");
  const [reason, setReason] = useState<string | null>(null);
  const [subscribedJob, setSubscribedJob] = useState(jobId);
  const carried = useRef("");
  const rawCarried = useRef("");
  const offset = useRef(0);

  // Callbacks are read through refs so that a caller passing an inline function
  // does not tear down and re-open the EventSource on every render.
  const onRawChunkRef = useRef(onRawChunk);
  const onFinishedRef = useRef(onFinished);
  useEffect(() => {
    onRawChunkRef.current = onRawChunk;
    onFinishedRef.current = onFinished;
  });

  // A new job resets the transcript before its first paint, rather than showing
  // the previous run's entries until an effect catches up.
  if (subscribedJob !== jobId) {
    setSubscribedJob(jobId);
    setEntries([]);
    setState("connecting");
    setReason(null);
  }

  useEffect(() => {
    let disposed = false;
    let source: EventSource | null = null;

    carried.current = "";
    rawCarried.current = "";
    offset.current = 0;

    (async () => {
      let replay: TerminalReplay;
      try {
        const response = await proxyFetch(endpoints.jobTerminal(jobId));
        if (!response.ok) throw new Error(`the API answered ${response.status}`);
        replay = (await response.json()) as TerminalReplay;
      } catch (error) {
        // Without this the hook sat on "connecting" for ever and the rejection
        // went unhandled: a dead API looked identical to a slow one.
        if (disposed) return;
        setState("unavailable");
        setReason(
          `Could not load this run's recording — ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
        return;
      }
      if (disposed) return;

      if (!replay.available) {
        setState("unavailable");
        setReason(replay.reason ?? null);
        return;
      }

      if (replay.data) {
        const decoded = decodeBase64Recording(replay.data);
        if (parseEntries) {
          const first = parseStream(decoded, "");
          carried.current = first.remainder;
          setEntries(first.entries);
        }
        const rawFirst = renderStream(decoded, "", true);
        rawCarried.current = rawFirst.remainder;
        if (rawFirst.lines) onRawChunkRef.current?.(rawFirst.lines);
        offset.current = replay.bytes ?? decoded.length;
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
        const chunk = decodeBase64Recording((event as MessageEvent).data);
        offset.current += chunk.length;

        if (parseEntries) {
          const next = parseStream(chunk, carried.current);
          carried.current = next.remainder;
          if (next.entries.length) {
            setEntries((prev) => mergeEntries(prev, next.entries));
          }
        }

        const rawNext = renderStream(chunk, rawCarried.current, true);
        rawCarried.current = rawNext.remainder;
        if (rawNext.lines) onRawChunkRef.current?.(rawNext.lines);
      });

      source.addEventListener("end", (event) => {
        setState("ended");
        source?.close();
        onFinishedRef.current?.((event as MessageEvent).data);
      });

      source.onerror = () => {
        if (source?.readyState === EventSource.CLOSED) setState("ended");
      };
    })();

    return () => {
      disposed = true;
      source?.close();
    };
  }, [jobId, parseEntries]);

  return { entries, state, reason };
}
