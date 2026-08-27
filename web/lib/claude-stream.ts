/**
 * Turning the CLI's own event stream into terminal lines.
 *
 * `claude --print` on a pty writes only the final answer, so there is nothing to
 * watch during a run; `--output-format stream-json --verbose` makes it report
 * each tool call as it happens. That JSON is the real process output, and this
 * renders one line per event — every line corresponds to something the process
 * actually did. Nothing is invented, and the raw stream is one toggle away.
 */

const DIM = "\x1b[2m";
const RESET = "\x1b[0m";
const CYAN = "\x1b[36m";
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const RED = "\x1b[31m";
const BOLD = "\x1b[1m";

export interface StreamRender {
  /** Terminal-ready text, newline-terminated. */
  lines: string;
  /** Leftover bytes of a JSON line that has not fully arrived yet. */
  remainder: string;
}

/**
 * The event's own timestamp, not the moment the browser parsed it.
 *
 * Replaying a finished run parses every event in the same millisecond, so
 * stamping parse time gives a whole session one identical clock — a number that
 * looks like information and is not. Falling back to now is only for the rare
 * event that carries no time of its own.
 */
function clock(event?: Record<string, any>): string {
  const stamp = event?.timestamp ?? event?.message?.timestamp;
  const when = stamp ? new Date(stamp) : new Date();
  const text = Number.isNaN(when.getTime())
    ? new Date().toLocaleTimeString([], { hour12: false })
    : when.toLocaleTimeString([], { hour12: false });
  return `${DIM}${text}${RESET}`;
}

function summariseInput(name: string, input: Record<string, unknown>): string {
  // The arguments that identify what a call is actually doing, not all of them.
  const interesting = ["file_path", "path", "query", "page_range", "pages", "part_number", "command", "project"];
  for (const key of interesting) {
    const value = input?.[key];
    if (typeof value === "string" && value) {
      const short = value.length > 60 ? `${value.slice(0, 57)}…` : value;
      return `${DIM}${short.replace(/\s+/g, " ")}${RESET}`;
    }
    if (typeof value === "number") return `${DIM}${value}${RESET}`;
  }
  return "";
}

function renderEvent(event: Record<string, any>): string[] {
  const out: string[] = [];
  const at = clock(event);

  switch (event.type) {
    case "system": {
      if (event.subtype === "init") {
        const tools = Array.isArray(event.tools) ? event.tools.length : 0;
        const servers = Array.isArray(event.mcp_servers)
          ? event.mcp_servers.map((s: any) => `${s.name}:${s.status}`).join(" ")
          : "";
        out.push(`${at} ${BOLD}session${RESET} ${DIM}model${RESET} ${event.model ?? "?"} ${DIM}tools${RESET} ${tools}`);
        if (servers) out.push(`${at} ${BOLD}mcp${RESET}     ${servers}`);
      } else if (event.subtype === "error") {
        out.push(`${at} ${RED}error${RESET}   ${String(event.message ?? "").slice(0, 200)}`);
      }
      break;
    }
    case "assistant": {
      for (const block of event.message?.content ?? []) {
        if (block.type === "tool_use") {
          out.push(`${at} ${CYAN}call${RESET}    ${block.name} ${summariseInput(block.name, block.input ?? {})}`);
        } else if (block.type === "text" && block.text?.trim()) {
          for (const line of block.text.trimEnd().split("\n")) {
            out.push(`${at} ${DIM}·${RESET}       ${line}`);
          }
        }
      }
      break;
    }
    case "user": {
      for (const block of event.message?.content ?? []) {
        if (block.type !== "tool_result") continue;
        const body = typeof block.content === "string"
          ? block.content
          : JSON.stringify(block.content ?? "");
        const size = body.length;
        const tone = block.is_error ? RED : GREEN;
        const label = block.is_error ? "failed" : "ok";
        out.push(`${at} ${tone}${label}${RESET}${block.is_error ? "  " : "      "}${DIM}${size.toLocaleString()} chars${RESET}`);
        if (block.is_error) {
          out.push(`${at} ${RED}│${RESET}       ${body.slice(0, 300).replace(/\s+/g, " ")}`);
        }
      }
      break;
    }
    case "result": {
      const seconds = event.duration_ms ? (event.duration_ms / 1000).toFixed(1) : "?";
      const tone = event.is_error ? RED : GREEN;
      out.push(
        `${at} ${tone}${BOLD}done${RESET}    ${event.num_turns ?? "?"} turns in ${seconds}s` +
          (event.total_cost_usd ? ` ${DIM}$${Number(event.total_cost_usd).toFixed(3)}${RESET}` : ""),
      );
      break;
    }
    case "rate_limit_event": {
      out.push(`${at} ${YELLOW}limit${RESET}   ${String(event.subtype ?? "rate limit")}`);
      break;
    }
    default:
      break;
  }
  return out;
}

/** Render whatever complete JSON lines are present; keep the rest for next time. */
export function renderStream(chunk: string, carried = "", raw = false): StreamRender {
  const buffered = carried + chunk;
  const pieces = buffered.split("\n");
  const remainder = pieces.pop() ?? "";

  if (raw) return { lines: pieces.join("\r\n") + (pieces.length ? "\r\n" : ""), remainder };

  const rendered: string[] = [];
  for (const piece of pieces) {
    const trimmed = piece.trim();
    if (!trimmed) continue;
    if (!trimmed.startsWith("{")) {
      // Anything the CLI wrote that is not an event - keep it verbatim.
      rendered.push(`${DIM}${trimmed}${RESET}`);
      continue;
    }
    try {
      rendered.push(...renderEvent(JSON.parse(trimmed)));
    } catch {
      rendered.push(`${DIM}${trimmed.slice(0, 200)}${RESET}`);
    }
  }
  return {
    lines: rendered.length ? rendered.join("\r\n") + "\r\n" : "",
    remainder,
  };
}
