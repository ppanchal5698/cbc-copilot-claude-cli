"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import {
  PhoneCall,
  NotePencil,
  Question,
  X,
  PaperPlaneTilt,
  CheckCircle,
} from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { useUiState } from "@/components/shell/ui-state";

import { proxyFetcher } from "@/lib/proxy-fetcher";

const KINDS = [
  { key: "call", label: "Call", Icon: PhoneCall, placeholder: "Who did you speak to, and what was agreed?" },
  { key: "note", label: "Note", Icon: NotePencil, placeholder: "Anything the next person needs to know." },
  { key: "rfi", label: "RFI", Icon: Question, placeholder: "What is unclear, and who has to answer it?" },
] as const;

interface CallEntry {
  id: string;
  kind: "call" | "note" | "rfi";
  text: string;
  who: string;
  org?: string | null;
  ref?: string | null;
  createdAt: string;
  resolvedAt?: string | null;
}

/** Which stage the note was logged from, so it carries its own context. */
function stageFromPath(pathname: string): string {
  const stage = pathname.split("/").pop() ?? "";
  const labels: Record<string, string> = {
    intake: "Intake",
    extraction: "Extraction & entry",
    quote: "Quote",
    proposal: "Proposal",
  };
  return labels[stage] ?? "Workspace";
}

export function NotesDrawer({ code }: { code: string | null }) {
  const { notesOpen, closeNotes, notesRef, bumpNotes } = useUiState();
  const pathname = usePathname();
  const [kind, setKind] = useState<(typeof KINDS)[number]["key"]>("call");
  const [text, setText] = useState("");
  const [org, setOrg] = useState("");
  const [busy, setBusy] = useState(false);

  const { data, mutate } = useSWR<{ calls: CallEntry[]; count: number; openRfis: number }>(
    notesOpen && code ? `/api/proxy/projects/${code}/calls` : null,
    proxyFetcher,
  );

  if (!notesOpen) return null;

  const active = KINDS.find((entry) => entry.key === kind)!;

  async function submit() {
    if (!code) {
      toast.error("Open a bid first", { description: "Notes are saved against an estimate." });
      return;
    }
    if (!text.trim()) return;

    setBusy(true);
    const response = await fetch(`/api/proxy/projects/${code}/calls`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind,
        text: text.trim(),
        org: org.trim() || null,
        ref: notesRef ?? stageFromPath(pathname),
      }),
    });
    setBusy(false);

    if (!response.ok) {
      toast.error("Could not log that");
      return;
    }
    toast.success(`${active.label} logged`, { description: "It travels with the estimate." });
    setText("");
    setOrg("");
    mutate();
    bumpNotes();
  }

  async function resolve(entry: CallEntry) {
    await fetch(`/api/proxy/projects/${code}/calls/${entry.id}/resolve`, { method: "POST" });
    toast.success("RFI closed");
    mutate();
    bumpNotes();
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="flex-1" style={{ background: "rgba(0,0,0,0.5)" }} onClick={closeNotes} />

      <aside
        className="flex w-[460px] flex-col"
        style={{
          background: "var(--app-bg-2)",
          borderLeft: "1px solid var(--app-line)",
          boxShadow: "var(--app-sh-3)",
          animation: "slidein 0.18s ease both",
        }}
      >
        <div
          className="flex items-center gap-3 border-b px-5 py-4"
          style={{ borderColor: "var(--app-line)" }}
        >
          <span
            className="grid h-8 w-8 place-items-center rounded-lg"
            style={{ background: "var(--app-accent-soft)", color: "var(--app-accent)" }}
          >
            <PhoneCall size={17} weight="duotone" />
          </span>
          <span className="flex flex-1 flex-col leading-tight">
            <span className="text-[14px] font-semibold">Log a call or note</span>
            <span className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
              {code
                ? `Saved against ${code} · travels with the estimate`
                : "Open a bid to log against it"}
            </span>
          </span>
          <button onClick={closeNotes} aria-label="Close" style={{ color: "var(--app-tx-3)" }}>
            <X size={16} weight="bold" />
          </button>
        </div>

        <div className="border-b px-5 py-4" style={{ borderColor: "var(--app-line)" }}>
          <div className="flex gap-1.5">
            {KINDS.map((entry) => {
              const on = entry.key === kind;
              return (
                <button
                  key={entry.key}
                  onClick={() => setKind(entry.key)}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-[12.5px]"
                  style={{
                    background: on ? "var(--app-accent-soft)" : "transparent",
                    color: on ? "var(--app-accent)" : "var(--app-tx-2)",
                    border: `1px solid ${on ? "var(--app-accent-line)" : "var(--app-line)"}`,
                  }}
                >
                  <entry.Icon size={14} weight="duotone" />
                  {entry.label}
                </button>
              );
            })}
          </div>

          <input
            value={org}
            onChange={(event) => setOrg(event.target.value)}
            placeholder="Who it was with — GC, architect, vendor"
            className="mt-2.5 w-full rounded-md px-2.5 py-2 text-[12.5px] outline-none focus:ring-2"
            style={{
              background: "var(--app-panel-2)",
              border: "1px solid var(--app-line)",
              color: "var(--app-tx)",
            }}
          />

          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={active.placeholder}
            rows={4}
            className="mt-2 w-full resize-none rounded-md px-2.5 py-2 text-[12.5px] outline-none focus:ring-2"
            style={{
              background: "var(--app-panel-2)",
              border: "1px solid var(--app-line)",
              color: "var(--app-tx)",
            }}
          />

          <div className="mt-2.5 flex items-center gap-2">
            <span className="flex-1 text-[11px]" style={{ color: "var(--app-tx-3)" }}>
              Logged against {notesRef ?? stageFromPath(pathname)}
            </span>
            <button
              onClick={closeNotes}
              className="rounded-md px-3 py-1.5 text-[12px]"
              style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={busy || !text.trim()}
              className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-semibold disabled:opacity-50"
              style={{ background: "var(--app-accent)", color: "#fff" }}
            >
              <PaperPlaneTilt size={13} weight="duotone" />
              Log it
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto px-5 py-3">
          {(data?.calls ?? []).length === 0 ? (
            <p className="py-8 text-center text-[12px]" style={{ color: "var(--app-tx-3)" }}>
              Nothing logged on this bid yet.
            </p>
          ) : (
            (data?.calls ?? []).map((entry) => {
              const meta = KINDS.find((k) => k.key === entry.kind) ?? KINDS[0];
              const open = entry.kind === "rfi" && !entry.resolvedAt;
              return (
                <div
                  key={entry.id}
                  className="border-b py-3 last:border-b-0"
                  style={{ borderColor: "var(--app-line)" }}
                >
                  <div className="flex items-start gap-2.5">
                    <meta.Icon
                      size={15}
                      weight="duotone"
                      style={{ color: open ? "var(--app-warn)" : "var(--app-tx-3)" }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline gap-2">
                        <span className="text-[12.5px] font-semibold">{entry.who}</span>
                        {open && (
                          <span
                            className="rounded px-1.5 text-[10px]"
                            style={{ background: "var(--app-warn-soft)", color: "var(--app-warn)" }}
                          >
                            open RFI
                          </span>
                        )}
                      </div>
                      <div className="text-[10.5px]" style={{ color: "var(--app-tx-3)" }}>
                        {entry.org ? `${entry.org} · ` : ""}
                        {new Date(entry.createdAt).toLocaleString()}
                        {entry.ref ? ` · ${entry.ref}` : ""}
                      </div>
                      <p className="mt-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
                        {entry.text}
                      </p>
                    </div>
                    {open && (
                      <button
                        onClick={() => resolve(entry)}
                        title="Mark this RFI answered"
                        style={{ color: "var(--app-pos)" }}
                      >
                        <CheckCircle size={15} weight="duotone" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>
    </div>
  );
}
