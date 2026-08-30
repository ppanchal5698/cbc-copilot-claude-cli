"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Tray, FilePdf, UploadSimple, Trash } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import type { BidDocument, Job, UploadResult } from "@/lib/types";
import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
const KINDS = [
  { key: "plan", label: "Plan set" },
  { key: "spec", label: "Specification" },
  { key: "rfp", label: "RFP" },
  { key: "addendum", label: "Addendum" },
] as const;

export function UploadPanel({
  code,
  initialDocuments,
}: {
  code: string;
  initialDocuments: BidDocument[];
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<string>("plan");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<{ name: string; index: number; total: number } | null>(
    null,
  );

  const { data, mutate } = useSWR<{ documents: BidDocument[] }>(
    `/api/proxy/projects/${code}/documents`,
    proxyFetcher,
    { fallbackData: { documents: initialDocuments } },
  );
  const documents = data?.documents ?? [];

  const { data: jobData } = useSWR<{ jobs: Job[] }>(
    `/api/proxy/jobs?project=${code}&limit=1`,
    proxyFetcher,
    {
      refreshInterval: (latest) => {
        const current = latest?.jobs?.[0];
        return current?.status === "running" || current?.status === "queued" ? 5000 : 0;
      },
    },
  );
  const job = jobData?.jobs?.[0];

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    const queue = Array.from(files);
    setBusy(true);

    for (const [index, file] of queue.entries()) {
      // Bid sets run to hundreds of megabytes; naming the file and its place in
      // the queue is the difference between "working" and "frozen".
      setProgress({ name: file.name, index: index + 1, total: queue.length });

      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);

      try {
        const result = await proxyMutate<UploadResult>(
          `/api/proxy/projects/${code}/documents`,
          { form },
        );
        toast.success(`${file.name} received`, {
          description: `${result.document.pages ?? "?"} pages · Claude has been queued to read it.`,
        });
      } catch (problem) {
        toast.error(`${file.name} was not accepted`, { description: errorMessage(problem) });
      }
    }

    setProgress(null);
    setBusy(false);
    if (inputRef.current) inputRef.current.value = "";
    mutate();
    router.refresh();
  }

  async function remove(document: BidDocument) {
    if (
      !window.confirm(
        `Detach ${document.filename} from this bid? The file itself is kept — raw uploads are immutable.`,
      )
    ) {
      return;
    }
    try {
      await proxyMutate(`/api/proxy/projects/${code}/documents/${document.id}`, {
        method: "DELETE",
      });
      toast.success(`${document.filename} detached`, {
        description: "The file itself is kept — raw uploads are immutable.",
      });
      mutate();
      router.refresh();
    } catch (problem) {
      toast.error("Could not detach that document", { description: errorMessage(problem) });
    }
  }

  return (
    <div
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div
        className="flex flex-wrap items-center gap-3 border-b px-4 py-3.5"
        style={{ borderColor: "var(--app-line)" }}
      >
        <span className="text-[15px] font-semibold">Bid documents</span>
        <span className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
          {documents.length} file{documents.length === 1 ? "" : "s"}
          {job && (job.status === "running" || job.status === "queued")
            ? " · Claude is reading"
            : ""}
        </span>
        <span className="flex-1" />
        <div className="flex flex-wrap gap-1">
          {KINDS.map((entry) => (
            <button
              key={entry.key}
              onClick={() => setKind(entry.key)}
              className="rounded-md px-2.5 py-1 text-[11.5px]"
              style={{
                background: kind === entry.key ? "var(--app-accent-soft)" : "transparent",
                color: kind === entry.key ? "var(--app-accent)" : "var(--app-tx-2)",
                border: `1px solid ${kind === entry.key ? "var(--app-accent-line)" : "var(--app-line)"}`,
              }}
            >
              {entry.label}
            </button>
          ))}
        </div>
      </div>

      {documents.length > 0 && (
        <div className="overflow-x-auto">
          <div
            className="grid gap-3 border-b px-4 py-2 text-[10.5px] uppercase tracking-[0.07em]"
            style={{
              minWidth: 560,
              gridTemplateColumns: "minmax(200px,1fr) 90px 110px 110px 40px",
              borderColor: "var(--app-line)",
              color: "var(--app-tx-3)",
            }}
          >
            <span>File</span>
            <span>Pages</span>
            <span>Received</span>
            <span>State</span>
            <span />
          </div>
          {documents.map((document) => (
            <div
              key={document.id}
              className="grid items-center gap-3 border-b px-4 py-2.5 last:border-b-0"
              style={{
                minWidth: 560,
                gridTemplateColumns: "minmax(200px,1fr) 90px 110px 110px 40px",
                borderColor: "var(--app-line)",
              }}
            >
              <span className="flex min-w-0 items-center gap-2">
                <FilePdf size={16} weight="duotone" style={{ color: "#22d3ee" }} />
                <span className="flex min-w-0 flex-col leading-tight">
                  <span className="truncate text-[12.5px]">{document.filename}</span>
                  <span className="text-[10.5px]" style={{ color: "var(--app-tx-3)" }}>
                    {document.kind}
                  </span>
                </span>
              </span>
              <span className="tnum text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
                {document.pages ?? "—"}
              </span>
              <span className="text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                {new Date(document.uploadedAt).toLocaleDateString()}
              </span>
              <span
                className="text-[12px]"
                style={{
                  color: document.state === "read" ? "var(--app-pos)" : "var(--app-tx-2)",
                }}
              >
                {document.state}
              </span>
              <button
                onClick={() => remove(document)}
                aria-label={`Detach ${document.filename}`}
                style={{ color: "var(--app-tx-3)" }}
              >
                <Trash size={14} weight="duotone" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            setDragging(false);
          }
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          upload(event.dataTransfer.files);
        }}
        className="m-4 grid place-items-center gap-2 rounded-lg px-6 py-10 text-center transition"
        style={{
          border: `1.5px dashed ${dragging ? "var(--app-accent)" : "var(--app-line)"}`,
          background: dragging ? "var(--app-accent-soft)" : "transparent",
        }}
      >
        <Tray size={26} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
        <span className="text-[13.5px] font-semibold">
          {documents.length === 0 ? "No documents yet" : "Add another document"}
        </span>
        <span className="max-w-[460px] text-[12px]" style={{ color: "var(--app-tx-2)" }}>
          Drop the bid set in and the schedules, elevations and specs are read for you. Uploading a
          plan set is what notifies Claude — nothing else is needed.
        </span>

        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          multiple
          className="hidden"
          onChange={(event) => upload(event.target.files)}
        />
        <button
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="mt-1 flex items-center gap-1.5 rounded-md px-3.5 py-2 text-[12.5px] font-semibold disabled:opacity-60"
          style={{ background: "var(--app-accent)", color: "#fff" }}
        >
          <UploadSimple size={14} weight="bold" />
          {busy ? "Uploading…" : "Choose PDFs"}
        </button>

        {progress && (
          <span
            className="mt-1 text-[11.5px]"
            aria-live="polite"
            style={{ color: "var(--app-tx-2)" }}
          >
            Sending {progress.name}
            {progress.total > 1 ? ` (${progress.index} of ${progress.total})` : ""}…
          </span>
        )}
      </div>
    </div>
  );
}
