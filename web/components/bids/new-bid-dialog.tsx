"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { useDialog } from "@/hooks/use-dialog";
import { errorMessage, proxyMutate } from "@/lib/proxy-fetcher";
import type { Project } from "@/lib/types";

interface Field {
  key: string;
  label: string;
  placeholder: string;
  required?: boolean;
  hint?: string;
  type?: string;
}

const FIELDS: Field[] = [
  { key: "name", label: "Job name", placeholder: "Burger King #2379 — exterior & interior", required: true },
  { key: "brand", label: "Brand", placeholder: "Burger King" },
  { key: "location", label: "Location", placeholder: "Cortlandt Manor, NY" },
  { key: "state", label: "State", placeholder: "NY", hint: "Two letters. Tax applies to OH and KY only." },
  { key: "gc", label: "General contractor", placeholder: "Cortlandt Builders LLC" },
  { key: "initiator", label: "Requested by", placeholder: "Rebecca Gabrich", hint: "The quote goes back to this person." },
  { key: "architect", label: "Architect", placeholder: "Coralic LLC" },
  { key: "bidDue", label: "Bid due", placeholder: "", type: "date" },
];

export function NewBidDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [autopilot, setAutopilot] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const close = useCallback(() => setOpen(false), []);
  const dialogRef = useDialog<HTMLFormElement>(open, close);

  async function create(event: React.FormEvent) {
    event.preventDefault();

    const errors: Record<string, string> = {};
    if (!values.name?.trim()) {
      errors.name = "Job name is required.";
    }
    if (values.state?.trim() && values.state.trim().length !== 2) {
      errors.state = "Use a two-letter state code (e.g. OH).";
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    const body = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value.trim() !== ""),
    );
    if (body.state) body.state = body.state.toUpperCase().slice(0, 2);

    setBusy(true);
    try {
      const project = await proxyMutate<Project>("/api/proxy/projects", {
        body: { ...body, autopilot },
      });
      toast.success(`${project.code} created`, { description: "Now add the bid documents." });
      setOpen(false);
      setValues({});
      setAutopilot(false);
      router.push(`/bids/${project.code}/intake`);
      router.refresh();
    } catch (problem) {
      toast.error("Could not create the bid", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-md px-3.5 py-2 text-[12.5px] font-semibold"
        style={{ background: "var(--app-accent)", color: "#fff" }}
      >
        <Plus size={14} weight="bold" />
        New bid
      </button>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center overflow-auto p-4 sm:p-6"
      style={{ background: "rgba(0,0,0,0.55)" }}
      onClick={(event) => event.target === event.currentTarget && setOpen(false)}
    >
      <form
        ref={dialogRef}
        onSubmit={create}
        noValidate
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-bid-title"
        className="anim-popin my-auto w-full max-w-[620px] rounded-xl p-5 sm:p-6"
        style={{
          background: "var(--app-panel)",
          border: "1px solid var(--app-line)",
          boxShadow: "var(--app-sh-3)",
        }}
      >
        <h2 id="new-bid-title" className="text-[16px] font-semibold">
          New bid
        </h2>
        <p className="mt-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
          A CBC number is assigned automatically. Everything else can be filled in later.
        </p>

        <div className="mt-5 grid gap-x-4 gap-y-3.5 sm:grid-cols-2">
          {FIELDS.map((field) => (
            <label
              key={field.key}
              htmlFor={`new-bid-${field.key}`}
              className={field.key === "name" ? "block sm:col-span-2" : "block"}
            >
              <span
                className="block text-[11px] uppercase tracking-[0.07em]"
                style={{ color: "var(--app-tx-3)" }}
              >
                {field.label}
                {field.required && <span style={{ color: "var(--app-neg)" }}> *</span>}
              </span>
              <input
                id={`new-bid-${field.key}`}
                type={field.type ?? "text"}
                aria-invalid={fieldErrors[field.key] ? true : undefined}
                aria-describedby={
                  fieldErrors[field.key]
                    ? `new-bid-${field.key}-error`
                    : field.hint
                      ? `new-bid-${field.key}-hint`
                      : undefined
                }
                placeholder={field.placeholder}
                value={values[field.key] ?? ""}
                onChange={(event) => {
                  setValues((current) => ({ ...current, [field.key]: event.target.value }));
                  if (fieldErrors[field.key]) {
                    setFieldErrors((current) => {
                      const next = { ...current };
                      delete next[field.key];
                      return next;
                    });
                  }
                }}
                className="mt-1 w-full rounded-md px-2.5 py-2 text-[13px] outline-none focus:ring-2"
                style={{
                  background: "var(--app-panel-2)",
                  border: `1px solid ${fieldErrors[field.key] ? "var(--app-neg-line)" : "var(--app-line)"}`,
                  color: "var(--app-tx)",
                }}
              />
              {fieldErrors[field.key] && (
                <span
                  id={`new-bid-${field.key}-error`}
                  className="mt-1 block text-[11px]"
                  style={{ color: "var(--app-neg)" }}
                >
                  {fieldErrors[field.key]}
                </span>
              )}
              {field.hint && (
                <span
                  id={`new-bid-${field.key}-hint`}
                  className="mt-1 block text-[10.5px]"
                  style={{ color: "var(--app-tx-3)" }}
                >
                  {field.hint}
                </span>
              )}
            </label>
          ))}
        </div>

        <label
          className="mt-5 flex cursor-pointer items-start gap-2.5 rounded-lg px-3 py-2.5"
          style={{ background: "var(--app-panel-2)", border: "1px solid var(--app-line)" }}
        >
          <input
            type="checkbox"
            checked={autopilot}
            onChange={(event) => setAutopilot(event.target.checked)}
            className="mt-0.5"
          />
          <span className="flex flex-col leading-snug">
            <span className="text-[12.5px] font-semibold">Run the whole pipeline on upload</span>
            <span className="text-[11.5px]" style={{ color: "var(--app-tx-2)" }}>
              One pass from intake to a draft proposal, without stopping for you to
              confirm the openings. They are priced before anyone checks them, and
              anything uncertain is flagged for review at the end. Nothing is ever sent.
            </span>
          </span>
        </label>

        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-md px-3.5 py-2 text-[12.5px]"
            style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded-md px-3.5 py-2 text-[12.5px] font-semibold disabled:opacity-60"
            style={{ background: "var(--app-accent)", color: "#fff" }}
          >
            {busy ? "Creating…" : "Create bid"}
          </button>
        </div>
      </form>
    </div>
  );
}
