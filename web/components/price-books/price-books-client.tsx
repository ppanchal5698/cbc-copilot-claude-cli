"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import {
  Books,
  UploadSimple,
  Trash,
  CheckCircle,
  Plus,
  Envelope,
} from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { formatMoney } from "@/lib/format";
import type { PriceBook, Product } from "@/lib/types";

import { proxyFetcher } from "@/lib/proxy-fetcher";

function formatMultiplier(value: number | null | undefined): string {
  return typeof value === "number" && !Number.isNaN(value) ? value.toFixed(3) : "—";
}

interface ListResponse {
  priceBooks: PriceBook[];
  counts: { total: number; stale: number; undated: number };
  stewardship: { owner: string | null; cadence: string | null; note: string };
}

export function PriceBooksClient() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data, error, mutate } = useSWR<ListResponse>("/api/proxy/price-books", proxyFetcher);
  const { data: detail, mutate: mutateDetail } = useSWR<{
    priceBook: PriceBook;
    parts: Product[];
    partCount: number;
  }>(selectedId ? `/api/proxy/price-books/${selectedId}` : null, proxyFetcher);

  const books = data?.priceBooks ?? [];
  const selected = detail?.priceBook;

  async function upload(files: FileList | null) {
    if (!files?.length || !selectedId) return;
    const form = new FormData();
    form.append("file", files[0]);

    const response = await fetch(`/api/proxy/price-books/${selectedId}/file`, {
      method: "POST",
      body: form,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      toast.error("Upload failed", { description: String(body.detail) });
      return;
    }
    toast.success("Sheet uploaded", {
      description: "Claude has been queued to read it into the catalog.",
    });
    if (fileRef.current) fileRef.current.value = "";
    mutate();
    mutateDetail();
  }

  async function patch(body: Record<string, unknown>, success: string) {
    const response = await fetch(`/api/proxy/price-books/${selectedId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      toast.error("Could not save that");
      return;
    }
    toast.success(success);
    mutate();
    mutateDetail();
  }

  /** Record that purchasing has been asked for a newer sheet. Sends nothing. */
  async function requestSheet() {
    if (!selected) return;
    const note = `Updated sheet requested ${new Date().toLocaleDateString()}`;
    const response = await fetch(`/api/proxy/price-books/${selectedId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    });
    if (!response.ok) {
      toast.error("Could not record the request");
      return;
    }
    toast.success("Request recorded against the program", {
      description: "Nothing was emailed — tell purchasing directly.",
    });
    mutate();
    mutateDetail();
  }

  async function markReviewed() {
    const response = await fetch(`/api/proxy/price-books/${selectedId}/mark-reviewed`, {
      method: "POST",
    });
    if (!response.ok) {
      toast.error("Could not record the review");
      return;
    }
    toast.success("Marked as reviewed today");
    mutate();
    mutateDetail();
  }

  async function remove() {
    if (!selected) return;
    const response = await fetch(`/api/proxy/price-books/${selectedId}`, { method: "DELETE" });
    if (!response.ok) {
      toast.error("Could not remove that program");
      return;
    }
    toast.success(`${selected.vendor} removed`, {
      description: "Parts priced under it are kept and marked orphaned.",
    });
    setSelectedId(null);
    mutate();
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/proxy/price-books", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        vendor: String(form.get("vendor") ?? "").trim(),
        program: String(form.get("program") ?? "").trim() || null,
        multiplier: form.get("multiplier") ? Number(form.get("multiplier")) : null,
        effective: String(form.get("effective") ?? "") || null,
      }),
    });
    if (!response.ok) {
      toast.error("Could not add that program");
      return;
    }
    toast.success("Program added");
    setAdding(false);
    mutate();
  }

  return (
    <main className="relative flex min-h-0 flex-1 gap-4 overflow-hidden p-4">
      {error && (
        <div
          className="absolute inset-x-4 top-4 z-10 rounded-lg px-4 py-3 text-[12.5px]"
          style={{
            background: "var(--app-neg-soft)",
            border: "1px solid var(--app-neg-line)",
            color: "var(--app-neg)",
          }}
        >
          Could not load price books: {error.message}
        </div>
      )}
      <section className="flex w-[340px] shrink-0 flex-col gap-3">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-[18px] font-semibold">Price books</h1>
            <p className="mt-0.5 text-[11.5px]" style={{ color: "var(--app-tx-2)" }}>
              {data?.counts.total ?? 0} programs · {data?.counts.stale ?? 0} past review
            </p>
          </div>
          <button
            onClick={() => setAdding((current) => !current)}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px]"
            style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
          >
            <Plus size={13} weight="bold" />
            Add
          </button>
        </div>

        {adding && (
          <form
            onSubmit={create}
            className="anim-fadein flex flex-col gap-2 rounded-xl p-3"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            {[
              { name: "vendor", placeholder: "Vendor key, e.g. hager", required: true },
              { name: "program", placeholder: "Program name" },
              { name: "multiplier", placeholder: "Multiplier, e.g. 0.29", type: "number" },
              { name: "effective", placeholder: "Effective date", type: "date" },
            ].map((field) => (
              <input
                key={field.name}
                name={field.name}
                type={field.type ?? "text"}
                step="0.001"
                required={field.required}
                placeholder={field.placeholder}
                className="rounded-md px-2.5 py-2 text-[12.5px] outline-none focus:ring-2"
                style={{
                  background: "var(--app-panel-2)",
                  border: "1px solid var(--app-line)",
                  color: "var(--app-tx)",
                }}
              />
            ))}
            <button
              type="submit"
              className="rounded-md py-2 text-[12.5px] font-semibold"
              style={{ background: "var(--app-accent)", color: "#fff" }}
            >
              Add program
            </button>
          </form>
        )}

        <div
          className="min-h-0 flex-1 overflow-auto rounded-xl"
          style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
        >
          {books.map((book) => (
            <button
              key={book.id}
              onClick={() => setSelectedId(book.id)}
              className="flex w-full items-center gap-3 border-b px-4 py-3 text-left last:border-b-0"
              style={{
                borderColor: "var(--app-line)",
                background: selectedId === book.id ? "var(--app-panel-2)" : "transparent",
                borderLeft: `3px solid ${selectedId === book.id ? "var(--app-accent)" : "transparent"}`,
              }}
            >
              <span className="flex min-w-0 flex-1 flex-col leading-tight">
                <span className="truncate text-[13px] font-semibold capitalize">
                  {book.displayName ?? book.vendor}
                </span>
                <span className="truncate text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                  {book.program ?? book.kind ?? "—"}
                </span>
                <span
                  className="mt-0.5 text-[10.5px]"
                  style={{ color: book.stale || book.undated ? "var(--app-neg)" : "var(--app-tx-3)" }}
                >
                  {book.undated
                    ? "No effective date"
                    : book.stale
                      ? `Past review · ${book.effective}`
                      : `Reviewed ${book.lastReviewed ?? book.effective}`}
                </span>
              </span>
              <span className="tnum text-[14px] font-semibold">
                {formatMultiplier(book.multiplier)}
              </span>
            </button>
          ))}
        </div>
      </section>

      <section
        className="flex min-w-0 flex-1 flex-col overflow-auto rounded-xl"
        style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
      >
        {!selected ? (
          <div className="grid flex-1 place-items-center gap-2 px-6 text-center">
            <Books size={26} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
            <span className="text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
              Pick a program to see its multiplier, its parts, and to upload a newer sheet.
            </span>
          </div>
        ) : (
          <div className="p-6">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-[22px] font-semibold capitalize">
                  {selected.displayName ?? selected.vendor}
                </h2>
                <p className="mt-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
                  {selected.program ?? "—"}
                  {selected.account ? ` · account ${selected.account}` : ""}
                </p>
              </div>
              <div className="text-right">
                <span
                  className="block text-[10.5px] uppercase tracking-[0.07em]"
                  style={{ color: "var(--app-tx-3)" }}
                >
                  Multiplier
                </span>
                <span className="tnum text-[32px] font-bold leading-none">
                  {formatMultiplier(selected.multiplier)}
                </span>
              </div>
            </div>

            <div
              className="mt-6 grid grid-cols-4 gap-4 rounded-lg border p-4"
              style={{ borderColor: "var(--app-line)" }}
            >
              {[
                ["Effective", selected.effective ?? "not recorded"],
                ["Protected through", selected.protectedThrough ?? "—"],
                ["Last reviewed", selected.lastReviewed ?? "never"],
                ["Steward", selected.steward ?? "UNASSIGNED"],
              ].map(([label, value]) => (
                <div key={label}>
                  <span
                    className="block text-[10.5px] uppercase tracking-[0.07em]"
                    style={{ color: "var(--app-tx-3)" }}
                  >
                    {label}
                  </span>
                  <span
                    className="mt-0.5 block text-[14px] font-semibold"
                    style={{
                      color: value === "UNASSIGNED" || value === "never" ? "var(--app-neg)" : "var(--app-tx)",
                    }}
                  >
                    {value}
                  </span>
                </div>
              ))}
            </div>

            {(selected.stale || selected.undated) && (
              <p
                className="mt-3 rounded-md px-3 py-2 text-[11.5px]"
                style={{
                  background: "var(--app-neg-soft)",
                  border: "1px solid var(--app-neg-line)",
                  color: "var(--app-neg)",
                }}
              >
                {selected.undated
                  ? "No effective date on file, so staleness cannot be judged."
                  : `This sheet is ${selected.ageDays} days old. Quotes priced from it may be wrong.`}{" "}
                No owner or refresh cadence has been assigned (NFR-10 is open).
              </p>
            )}

            <div className="mt-5 flex items-end gap-3">
              <label className="flex flex-col">
                <span className="text-[10.5px] uppercase tracking-[0.07em]" style={{ color: "var(--app-tx-3)" }}>
                  Multiplier
                </span>
                <input
                  type="number"
                  step="0.001"
                  defaultValue={selected.multiplier ?? ""}
                  key={selected.id}
                  onBlur={(event) => {
                    const next = Number(event.target.value);
                    if (!Number.isNaN(next) && next !== selected.multiplier) {
                      patch({ multiplier: next }, "Multiplier updated and parts repriced");
                    }
                  }}
                  className="tnum mt-1 w-[120px] rounded-md px-2.5 py-2 text-[13px] outline-none focus:ring-2"
                  style={{
                    background: "var(--app-panel-2)",
                    border: "1px solid var(--app-line)",
                    color: "var(--app-tx)",
                  }}
                />
              </label>

              <input
                ref={fileRef}
                type="file"
                className="hidden"
                onChange={(event) => upload(event.target.files)}
              />
              <button
                onClick={() => fileRef.current?.click()}
                className="flex items-center gap-1.5 rounded-md px-3.5 py-2 text-[12.5px] font-semibold"
                style={{ background: "var(--app-accent)", color: "#fff" }}
              >
                <UploadSimple size={14} weight="bold" />
                Upload a newer sheet
              </button>
              <button
                onClick={requestSheet}
                className="flex items-center gap-1.5 rounded-md px-3.5 py-2 text-[12.5px]"
                style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
              >
                <Envelope size={14} weight="duotone" />
                Request an updated sheet
              </button>
              <button
                onClick={markReviewed}
                className="flex items-center gap-1.5 rounded-md px-3.5 py-2 text-[12.5px]"
                style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
              >
                <CheckCircle size={14} weight="duotone" />
                Mark as reviewed today
              </button>
              <span className="flex-1" />
              <button
                onClick={remove}
                className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px]"
                style={{ border: "1px solid var(--app-neg-line)", color: "var(--app-neg)" }}
              >
                <Trash size={14} weight="duotone" />
                Remove
              </button>
            </div>

            <p className="mt-3 text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
              Changing the multiplier reprices every part on this program. Uploading a sheet queues
              Claude to read it into the catalog, so the next bid prices off the newest data.
            </p>

            <div className="mt-6">
              <span
                className="block text-[10.5px] uppercase tracking-[0.07em]"
                style={{ color: "var(--app-tx-3)" }}
              >
                Priced under this program ({detail?.partCount ?? 0})
              </span>

              {(detail?.parts ?? []).length === 0 ? (
                <p className="mt-2 text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                  No catalog parts point at this program yet.
                </p>
              ) : (
                <div className="mt-2">
                  <div
                    className="grid gap-3 border-b py-2 text-[10.5px] uppercase tracking-[0.07em]"
                    style={{
                      gridTemplateColumns: "230px 1fr 100px 100px",
                      borderColor: "var(--app-line)",
                      color: "var(--app-tx-3)",
                    }}
                  >
                    <span>Part</span>
                    <span>Description</span>
                    <span className="text-right">List</span>
                    <span className="text-right">Net</span>
                  </div>
                  {(detail?.parts ?? []).map((part) => (
                    <div
                      key={part.id}
                      className="grid items-center gap-3 border-b py-2 last:border-b-0"
                      style={{ gridTemplateColumns: "230px 1fr 100px 100px", borderColor: "var(--app-line)" }}
                    >
                      <span className="truncate text-[12.5px] font-medium">{part.part}</span>
                      <span className="truncate text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
                        {part.description}
                      </span>
                      <span className="tnum text-right text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
                        {part.listPrice === null ? "—" : `$${formatMoney(part.listPrice)}`}
                      </span>
                      <span className="tnum text-right text-[12.5px] font-semibold">
                        {part.cost === null ? "—" : `$${formatMoney(part.cost)}`}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
