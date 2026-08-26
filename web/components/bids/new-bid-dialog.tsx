"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

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

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);

    const body = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value.trim() !== ""),
    );
    if (body.state) body.state = body.state.toUpperCase().slice(0, 2);

    const response = await fetch("/api/proxy/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const detail = await response.json().catch(() => ({ detail: response.statusText }));
      toast.error("Could not create the bid", { description: String(detail.detail) });
      setBusy(false);
      return;
    }

    const project = await response.json();
    toast.success(`${project.code} created`, { description: "Now add the bid documents." });
    setOpen(false);
    setBusy(false);
    router.push(`/bids/${project.code}/intake`);
    router.refresh();
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
      className="fixed inset-0 z-50 grid place-items-center p-6"
      style={{ background: "rgba(0,0,0,0.55)" }}
      onClick={(event) => event.target === event.currentTarget && setOpen(false)}
    >
      <form
        onSubmit={create}
        className="anim-popin w-full max-w-[620px] rounded-xl p-6"
        style={{
          background: "var(--app-panel)",
          border: "1px solid var(--app-line)",
          boxShadow: "var(--app-sh-3)",
        }}
      >
        <h2 className="text-[16px] font-semibold">New bid</h2>
        <p className="mt-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
          A CBC number is assigned automatically. Everything else can be filled in later.
        </p>

        <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3.5">
          {FIELDS.map((field) => (
            <label
              key={field.key}
              className={field.key === "name" ? "col-span-2 block" : "block"}
            >
              <span
                className="block text-[11px] uppercase tracking-[0.07em]"
                style={{ color: "var(--app-tx-3)" }}
              >
                {field.label}
                {field.required && <span style={{ color: "var(--app-neg)" }}> *</span>}
              </span>
              <input
                type={field.type ?? "text"}
                required={field.required}
                placeholder={field.placeholder}
                value={values[field.key] ?? ""}
                onChange={(event) =>
                  setValues((current) => ({ ...current, [field.key]: event.target.value }))
                }
                className="mt-1 w-full rounded-md px-2.5 py-2 text-[13px] outline-none focus:ring-2"
                style={{
                  background: "var(--app-panel-2)",
                  border: "1px solid var(--app-line)",
                  color: "var(--app-tx)",
                }}
              />
              {field.hint && (
                <span className="mt-1 block text-[10.5px]" style={{ color: "var(--app-tx-3)" }}>
                  {field.hint}
                </span>
              )}
            </label>
          ))}
        </div>

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
