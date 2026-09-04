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
  { key: "name", label: "Job name", placeholder: "e.g. Burger King #2379 — exterior & interior", required: true },
  { key: "brand", label: "Brand", placeholder: "e.g. Burger King" },
  { key: "location", label: "Location", placeholder: "e.g. Cortlandt Manor, NY" },
  { key: "state", label: "State", placeholder: "e.g. NY", hint: "Two letters. Tax applies to OH and KY only." },
  { key: "gc", label: "General contractor", placeholder: "e.g. Cortlandt Builders LLC" },
  { key: "initiator", label: "Requested by", placeholder: "e.g. Rebecca Gabrich", hint: "The quote goes back to this person." },
  { key: "architect", label: "Architect", placeholder: "e.g. Coralic LLC" },
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
        className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-bold bg-brand-primary text-white hover:bg-brand-primary/90 transition-colors shadow-sm"
      >
        <Plus size={16} weight="bold" />
        New bid
      </button>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center overflow-auto p-4 sm:p-6 bg-black/55 backdrop-blur-sm"
      onClick={(event) => event.target === event.currentTarget && setOpen(false)}
    >
      <form
        ref={dialogRef}
        onSubmit={create}
        noValidate
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-bid-title"
        className="anim-popin my-auto w-full max-w-[620px] rounded-2xl p-6 sm:p-8 bg-panel border border-subtle shadow-2xl"
      >
        <h2 id="new-bid-title" className="text-[18px] font-bold text-tx-primary tracking-tight">
          New bid
        </h2>
        <p className="mt-1.5 text-[13px] font-medium text-tx-secondary leading-relaxed">
          A CBC number is assigned automatically. Everything else can be filled in later.
        </p>

        <div className="mt-6 grid gap-x-5 gap-y-4 sm:grid-cols-2">
          {FIELDS.map((field) => (
            <label
              key={field.key}
              htmlFor={`new-bid-${field.key}`}
              className={field.key === "name" ? "block sm:col-span-2" : "block"}
            >
              <span className="block text-[11px] font-bold uppercase tracking-widest text-tx-muted">
                {field.label}
                {field.required && <span className="text-status-error"> *</span>}
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
                className={`mt-1.5 w-full rounded-lg px-3 py-2.5 text-[13.5px] font-medium outline-none placeholder:italic placeholder:opacity-50 transition-all shadow-sm ${
                  fieldErrors[field.key]
                    ? "bg-status-error-soft border border-status-error/30 text-status-error focus:ring-2 focus:ring-status-error/30"
                    : "bg-background border border-subtle text-tx-primary focus:ring-2 focus:ring-brand-border focus:border-brand-primary/30"
                }`}
              />
              {fieldErrors[field.key] && (
                <span
                  id={`new-bid-${field.key}-error`}
                  className="mt-1.5 block text-[11.5px] font-medium text-status-error"
                >
                  {fieldErrors[field.key]}
                </span>
              )}
              {field.hint && (
                <span
                  id={`new-bid-${field.key}-hint`}
                  className="mt-1.5 block text-[11px] font-medium text-tx-muted"
                >
                  {field.hint}
                </span>
              )}
            </label>
          ))}
        </div>

        <label
          className="mt-6 flex cursor-pointer items-start gap-3 rounded-xl px-4 py-3.5 bg-panel-muted border border-subtle hover:bg-background/50 transition-colors shadow-sm"
        >
          <input
            type="checkbox"
            checked={autopilot}
            onChange={(event) => setAutopilot(event.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-subtle text-brand-primary focus:ring-brand-primary"
          />
          <span className="flex flex-col leading-snug gap-1">
            <span className="text-[13.5px] font-bold text-tx-primary tracking-tight">Run the whole pipeline on upload</span>
            <span className="text-[12px] font-medium text-tx-secondary leading-relaxed">
              One pass from intake to a draft proposal, without stopping for you to
              confirm the openings. They are priced before anyone checks them, and
              anything uncertain is flagged for review at the end. Nothing is ever sent.
            </span>
          </span>
        </label>

        <div className="mt-8 flex items-center justify-end gap-3 pt-4 border-t border-subtle">
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-lg px-4 py-2 text-[13px] font-bold border border-subtle bg-background text-tx-secondary hover:bg-panel-muted hover:text-tx-primary transition-colors shadow-sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg px-5 py-2 text-[13px] font-bold disabled:opacity-50 bg-brand-primary text-white hover:bg-brand-primary/90 transition-colors shadow-sm"
          >
            {busy ? "Creating…" : "Create bid"}
          </button>
        </div>
      </form>
    </div>
  );
}
