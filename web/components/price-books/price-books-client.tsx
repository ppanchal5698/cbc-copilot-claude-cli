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

import { StatusBadge } from "@/components/ui/status-badge";
import { formatMoney } from "@/lib/format";
import type { PriceBookDetail, PriceBooksResponse } from "@/lib/types";

import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";

function formatMultiplier(value: number | null | undefined): string {
  return typeof value === "number" && !Number.isNaN(value) ? value.toFixed(3) : "—";
}

function categoryLabel(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function PriceBooksClient() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data, error, isLoading, mutate } = useSWR<PriceBooksResponse>(
    "/api/proxy/price-books",
    proxyFetcher,
  );
  const { data: detail, mutate: mutateDetail } = useSWR<PriceBookDetail>(
    selectedId ? `/api/proxy/price-books/${selectedId}` : null,
    proxyFetcher,
  );

  const books = data?.priceBooks ?? [];
  const selected = detail?.priceBook;
  const categoryEntries = Object.entries(selected?.categories ?? {}).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  const usesCategoryMultipliers = categoryEntries.length > 0;

  async function upload(files: FileList | null) {
    if (!files?.length || !selectedId) return;
    const file = files[0];
    const form = new FormData();
    form.append("file", file);

    // A price book is a large PDF. Without this the button simply sat there.
    setUploading(file.name);
    try {
      await proxyMutate(`/api/proxy/price-books/${selectedId}/file`, { form });
      toast.success("Sheet uploaded", {
        description: "Claude has been queued to read it into the catalog.",
      });
      mutate();
      mutateDetail();
    } catch (problem) {
      toast.error("Upload failed", { description: errorMessage(problem) });
    } finally {
      setUploading(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function patch(body: Record<string, unknown>, success: string) {
    setBusy(true);
    try {
      await proxyMutate(`/api/proxy/price-books/${selectedId}`, { method: "PATCH", body });
      toast.success(success);
      mutate();
      mutateDetail();
    } catch (problem) {
      toast.error("Could not save that", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  /** Record that purchasing has been asked for a newer sheet. Sends nothing. */
  async function requestSheet() {
    if (!selected) return;
    const note = `Updated sheet requested ${new Date().toLocaleDateString()}`;
    try {
      await proxyMutate(`/api/proxy/price-books/${selectedId}`, {
        method: "PATCH",
        body: { note },
      });
      toast.success("Request recorded against the program", {
        description: "Nothing was emailed — tell purchasing directly.",
      });
      mutate();
      mutateDetail();
    } catch (problem) {
      toast.error("Could not record the request", { description: errorMessage(problem) });
    }
  }

  async function markReviewed() {
    try {
      await proxyMutate(`/api/proxy/price-books/${selectedId}/mark-reviewed`);
      toast.success("Marked as reviewed today");
      mutate();
      mutateDetail();
    } catch (problem) {
      toast.error("Could not record the review", { description: errorMessage(problem) });
    }
  }

  async function remove() {
    if (!selected) return;
    if (
      !window.confirm(
        `Remove the ${selected.displayName ?? selected.vendor} program? Parts priced under it are kept and marked orphaned.`,
      )
    ) {
      return;
    }
    try {
      await proxyMutate(`/api/proxy/price-books/${selectedId}`, { method: "DELETE" });
      toast.success(`${selected.vendor} removed`, {
        description: "Parts priced under it are kept and marked orphaned.",
      });
      setSelectedId(null);
      mutate();
    } catch (problem) {
      toast.error("Could not remove that program", { description: errorMessage(problem) });
    }
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await proxyMutate("/api/proxy/price-books", {
        body: {
          vendor: String(form.get("vendor") ?? "").trim(),
          program: String(form.get("program") ?? "").trim() || null,
          multiplier: form.get("multiplier") ? Number(form.get("multiplier")) : null,
          effective: String(form.get("effective") ?? "") || null,
        },
      });
      toast.success("Program added");
      setAdding(false);
      mutate();
    } catch (problem) {
      toast.error("Could not add that program", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="relative flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 lg:flex-row lg:overflow-hidden">
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
      <section className="flex shrink-0 flex-col gap-3 lg:w-[340px]">
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
          className="min-h-[160px] flex-1 overflow-auto rounded-xl"
          style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
        >
          {isLoading && books.length === 0 && (
            <p className="px-4 py-8 text-center text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
              Reading the programs…
            </p>
          )}
          {!isLoading && !error && books.length === 0 && (
            <div className="grid place-items-center gap-1.5 px-5 py-10 text-center">
              <span className="text-[13px] font-semibold">No price books yet</span>
              <span className="text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                Add a vendor program, then upload its sheet. Every quote prices off these.
              </span>
            </div>
          )}
          {books.map((book) => (
            <button
              key={book.id}
              onClick={() => setSelectedId(book.id)}
              className="flex w-full items-center gap-3 border-b px-4 py-3 text-left transition last:border-b-0 hover:bg-[var(--app-panel-2)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--app-accent)]"
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
                {(book.stale || book.undated) && (
                  <StatusBadge variant="caution" className="mt-1">
                    {book.undated ? "No effective date" : "Past review"}
                  </StatusBadge>
                )}
                <span
                  className="mt-0.5 block text-[10.5px]"
                  style={{ color: "var(--app-tx-3)" }}
                >
                  {book.undated
                    ? "Upload or record an effective date"
                    : book.stale
                      ? `Effective ${book.effective}`
                      : `Reviewed ${book.lastReviewed ?? book.effective}`}
                </span>
              </span>
              <span className="tnum text-[14px] font-semibold">
                {book.categories && Object.keys(book.categories).length > 0
                  ? "Per cat."
                  : formatMultiplier(book.multiplier)}
              </span>
            </button>
          ))}
        </div>
      </section>

      <section
        className="flex min-w-0 flex-1 flex-col rounded-xl lg:overflow-auto"
        style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
      >
        {!selected ? (
          <div className="grid flex-1 place-items-center gap-2 px-6 py-16 text-center">
            <Books size={32} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
            <span className="text-[14px] font-semibold">Select a price book</span>
            <span className="max-w-[320px] text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
              Pick a program from the list to review its multiplier, parts, and upload a newer sheet.
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
                  {usesCategoryMultipliers ? "Category multipliers" : "Multiplier"}
                </span>
                <span className="tnum text-[32px] font-bold leading-none">
                  {usesCategoryMultipliers ? "Per category" : formatMultiplier(selected.multiplier)}
                </span>
              </div>
            </div>

            <div
              className="mt-6 grid grid-cols-2 gap-4 rounded-lg border p-4 xl:grid-cols-4"
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

            <div className="mt-5 flex flex-wrap items-end gap-3">
              {usesCategoryMultipliers ? (
                <div className="flex w-full flex-col gap-2">
                  <span
                    className="text-[10.5px] uppercase tracking-[0.07em]"
                    style={{ color: "var(--app-tx-3)" }}
                  >
                    Hager Advantage Program tiers
                  </span>
                  <div
                    className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3"
                    style={{ maxWidth: 720 }}
                  >
                    {categoryEntries.map(([key, value]) => (
                      <label key={key} className="flex flex-col">
                        <span className="text-[11px]" style={{ color: "var(--app-tx-2)" }}>
                          {categoryLabel(key)}
                        </span>
                        <input
                          type="number"
                          step="0.001"
                          defaultValue={value}
                          key={`${selected.id}-${key}`}
                          disabled={busy}
                          aria-label={`${categoryLabel(key)} multiplier`}
                          onBlur={(event) => {
                            const next = Number(event.target.value);
                            if (event.target.value.trim() === "" || Number.isNaN(next)) return;
                            if (next === value) return;
                            const categories = {
                              ...(selected.categories ?? {}),
                              [key]: next,
                            };
                            patch({ categories }, `${categoryLabel(key)} multiplier updated`);
                          }}
                          className="tnum mt-1 rounded-md px-2.5 py-2 text-[13px] outline-none focus:ring-2"
                          style={{
                            background: "var(--app-panel-2)",
                            border: "1px solid var(--app-line)",
                            color: "var(--app-tx)",
                          }}
                        />
                      </label>
                    ))}
                  </div>
                </div>
              ) : (
                <label className="flex flex-col">
                  <span
                    className="text-[10.5px] uppercase tracking-[0.07em]"
                    style={{ color: "var(--app-tx-3)" }}
                  >
                    Multiplier
                  </span>
                  <input
                    type="number"
                    step="0.001"
                    defaultValue={selected.multiplier ?? ""}
                    key={selected.id}
                    disabled={busy}
                    aria-label="Multiplier"
                    onBlur={(event) => {
                      const next = Number(event.target.value);
                      if (event.target.value.trim() === "") return;
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
              )}

              <input
                ref={fileRef}
                type="file"
                accept="application/pdf,.pdf,.csv,.xlsx"
                aria-label="Upload a newer price sheet"
                className="hidden"
                onChange={(event) => upload(event.target.files)}
              />
              <button
                onClick={() => fileRef.current?.click()}
                disabled={!!uploading}
                className="flex items-center gap-1.5 rounded-md px-3.5 py-2 text-[12.5px] font-semibold disabled:opacity-60"
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
              {usesCategoryMultipliers
                ? "Category multipliers sync to vendor_tiers.json and drive list × category pricing."
                : "Changing the multiplier reprices every part on this program."}{" "}
              Uploading a sheet queues Claude to read it into the catalog, so the next bid prices off
              the newest data.
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
                <div className="mt-2 overflow-x-auto">
                  <div
                    className="grid gap-3 border-b py-2 text-[10.5px] uppercase tracking-[0.07em]"
                    style={{
                      minWidth: 620,
                      gridTemplateColumns: "230px minmax(160px,1fr) 100px 100px",
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
                      style={{
                        minWidth: 620,
                        gridTemplateColumns: "230px minmax(160px,1fr) 100px 100px",
                        borderColor: "var(--app-line)",
                      }}
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
