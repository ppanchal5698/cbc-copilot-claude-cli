"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";

import { proxyFetcher } from "@/lib/proxy-fetcher";

interface AuditEntry {
  id: string;
  at: string;
  actor: string;
  action: string;
  note?: string | null;
}

export function AuditLogPanel() {
  const [project, setProject] = useState("");
  const query = project.trim()
    ? `/api/proxy/audit?limit=50&project=${encodeURIComponent(project.trim())}`
    : "/api/proxy/audit?limit=50";

  const { data, isLoading } = useSWR<{ entries: AuditEntry[]; total: number }>(
    query,
    proxyFetcher,
  );

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <h2 className="text-[15px] font-semibold">Audit log</h2>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Who changed what — admin and purchasing only.
        </p>
        <input
          value={project}
          onChange={(event) => setProject(event.target.value)}
          placeholder="Filter by bid code, e.g. bid_12"
          className="mt-3 w-full max-w-xs rounded-md px-2.5 py-1.5 text-[12px] outline-none"
          style={{
            background: "var(--app-panel-2)",
            border: "1px solid var(--app-line)",
            color: "var(--app-tx)",
          }}
        />
      </div>

      <div className="max-h-[420px] overflow-auto">
        {isLoading && (
          <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
            Loading…
          </p>
        )}
        {(data?.entries ?? []).map((entry) => (
          <div
            key={entry.id}
            className="flex gap-3 border-b px-4 py-2.5 last:border-b-0"
            style={{ borderColor: "var(--app-line)" }}
          >
            <time
              className="tnum shrink-0 text-[11px]"
              style={{ color: "var(--app-tx-3)", width: "132px" }}
            >
              {new Date(entry.at).toLocaleString()}
            </time>
            <span className="shrink-0 text-[11.5px] font-medium" style={{ width: "140px" }}>
              {entry.actor}
            </span>
            <span className="text-[12px]" style={{ color: "var(--app-tx)" }}>
              {entry.action}
              {entry.note ? ` — ${entry.note}` : ""}
            </span>
          </div>
        ))}
        {!isLoading && (data?.entries.length ?? 0) === 0 && (
          <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
            No entries yet.
          </p>
        )}
      </div>
      {data && (
        <p
          className="border-t px-4 py-2 text-[11px]"
          style={{ borderColor: "var(--app-line)", color: "var(--app-tx-3)" }}
        >
          Showing {data.entries.length} of {data.total}
        </p>
      )}
    </section>
  );
}

interface UserRow {
  id: string;
  email: string;
  name: string;
  initials: string;
  role: string;
}

export function UsersAdminPanel() {
  const { data, mutate } = useSWR<{ users: UserRow[] }>("/api/proxy/users", proxyFetcher);
  const [draft, setDraft] = useState({
    email: "",
    name: "",
    initials: "",
    role: "estimator",
    password: "",
  });
  const [busy, setBusy] = useState(false);

  async function createUser(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const response = await fetch("/api/proxy/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    });
    setBusy(false);
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      toast.error("Could not create user", { description: String(body.detail) });
      return;
    }
    toast.success(`${draft.email} added`);
    setDraft({ email: "", name: "", initials: "", role: "estimator", password: "" });
    mutate();
  }

  async function updateRole(user: UserRow, role: string) {
    const response = await fetch(`/api/proxy/users/${user.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (!response.ok) {
      toast.error("Could not update role");
      return;
    }
    mutate();
  }

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <h2 className="text-[15px] font-semibold">Users</h2>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Accounts and roles for this installation.
        </p>
      </div>

      <form
        onSubmit={createUser}
        className="grid gap-2 border-b px-4 py-3 sm:grid-cols-2"
        style={{ borderColor: "var(--app-line)" }}
      >
        {(
          [
            ["email", "Email", "email"],
            ["name", "Name", "text"],
            ["initials", "Initials", "text"],
            ["password", "Password", "password"],
          ] as const
        ).map(([key, label, type]) => (
          <label key={key} className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
            {label}
            <input
              type={type}
              required
              value={draft[key]}
              onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
              className="mt-1 block w-full rounded-md px-2.5 py-1.5 text-[12px] outline-none"
              style={{
                background: "var(--app-panel-2)",
                border: "1px solid var(--app-line)",
                color: "var(--app-tx)",
              }}
            />
          </label>
        ))}
        <label className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
          Role
          <select
            value={draft.role}
            onChange={(event) => setDraft({ ...draft, role: event.target.value })}
            className="mt-1 block w-full rounded-md px-2.5 py-1.5 text-[12px] outline-none"
            style={{
              background: "var(--app-panel-2)",
              border: "1px solid var(--app-line)",
              color: "var(--app-tx)",
            }}
          >
            <option value="estimator">estimator</option>
            <option value="purchasing">purchasing</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            disabled={busy}
            className="rounded-md px-4 py-2 text-[12px] font-semibold disabled:opacity-50"
            style={{ background: "var(--app-accent)", color: "#fff" }}
          >
            Add user
          </button>
        </div>
      </form>

      <div className="divide-y" style={{ borderColor: "var(--app-line)" }}>
        {(data?.users ?? []).map((user) => (
          <div key={user.id} className="flex items-center gap-3 px-4 py-2.5">
            <div className="flex-1">
              <div className="text-[13px] font-medium">{user.name}</div>
              <div className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
                {user.email}
              </div>
            </div>
            <select
              value={user.role}
              onChange={(event) => updateRole(user, event.target.value)}
              className="rounded-md px-2 py-1 text-[12px] outline-none"
              style={{
                background: "var(--app-panel-2)",
                border: "1px solid var(--app-line)",
                color: "var(--app-tx)",
              }}
            >
              <option value="estimator">estimator</option>
              <option value="purchasing">purchasing</option>
              <option value="admin">admin</option>
            </select>
          </div>
        ))}
      </div>
    </section>
  );
}
