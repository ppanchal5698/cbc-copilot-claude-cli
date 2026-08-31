"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";

import { useDebounced } from "@/hooks/use-debounced";
import { FetchError } from "@/components/ui/fetch-error";
import { endpoints } from "@/lib/endpoints";
import { swrKeys } from "@/lib/swr-keys";
import { errorMessage, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";
import type { AuditEntry, IntegrationsResponse, PipelineSettings, UserRow } from "@/lib/types";

export function AuditLogPanel() {
  const [project, setProject] = useState("");
  // Debounced: this used to issue a request on every keystroke of the filter.
  const settled = useDebounced(project.trim());
  const query = settled
    ? `/api/proxy/audit?limit=50&project=${encodeURIComponent(settled)}`
    : "/api/proxy/audit?limit=50";

  const { data, error, isLoading } = useSWR<{ entries: AuditEntry[]; total: number }>(
    query,
    proxyFetcher,
    { keepPreviousData: true },
  );

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <h2 className="text-[15px] font-semibold">Audit log</h2>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Who changed what — administrators only.
        </p>
        <input
          value={project}
          onChange={(event) => setProject(event.target.value)}
          placeholder="Filter by bid code, e.g. bid_12"
          aria-label="Filter the audit log by bid code"
          className="mt-3 w-full max-w-xs rounded-md px-2.5 py-1.5 text-[12px] outline-none"
          style={{
            background: "var(--app-panel-2)",
            border: "1px solid var(--app-line)",
            color: "var(--app-tx)",
          }}
        />
      </div>

      <div className="max-h-[420px] overflow-auto">
        {error && (
          <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-neg)" }}>
            Could not read the audit log: {errorMessage(error)}
          </p>
        )}
        {isLoading && !data && (
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
        {!isLoading && !error && (data?.entries.length ?? 0) === 0 && (
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

export function UsersAdminPanel() {
  const { data, error, isLoading, mutate } = useSWR<{ users: UserRow[] }>(
    "/api/proxy/users",
    proxyFetcher,
  );
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
    try {
      await proxyMutate("/api/proxy/users", { body: draft });
      toast.success(`${draft.email} added`);
      setDraft({ email: "", name: "", initials: "", role: "estimator", password: "" });
      mutate();
    } catch (problem) {
      toast.error("Could not create user", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  async function updateRole(user: UserRow, role: string) {
    try {
      await proxyMutate(`/api/proxy/users/${user.id}`, { method: "PATCH", body: { role } });
      toast.success(`${user.name} is now ${role}`);
      mutate();
    } catch (problem) {
      toast.error("Could not update role", { description: errorMessage(problem) });
      // Put the select back where it was; the change did not happen.
      mutate();
    }
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

      {error && (
        <FetchError
          title="Could not load users"
          error={error}
          onRetry={() => mutate()}
          compact
        />
      )}
      {isLoading && !data && !error && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Loading users…
        </p>
      )}

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
              aria-label={`Role for ${user.name}`}
              onChange={(event) => updateRole(user, event.target.value)}
              className="rounded-md px-2 py-1 text-[12px] outline-none"
              style={{
                background: "var(--app-panel-2)",
                border: "1px solid var(--app-line)",
                color: "var(--app-tx)",
              }}
            >
              <option value="estimator">estimator</option>
              <option value="admin">admin</option>
            </select>
          </div>
        ))}
      </div>
    </section>
  );
}

export function PipelineSettingsPanel() {
  const { data, error, isLoading, mutate } = useSWR<PipelineSettings>(
    swrKeys.pipelineSettings(),
    proxyFetcher,
  );
  const [busy, setBusy] = useState(false);

  async function toggleAutopilot() {
    if (!data) return;
    setBusy(true);
    try {
      await proxyMutate<PipelineSettings>(endpoints.pipelineSettings(), {
        method: "PUT",
        body: { autopilotDefault: !data.autopilotDefault },
      });
      toast.success(
        !data.autopilotDefault
          ? "Autopilot enabled for new bids"
          : "Autopilot disabled for new bids",
      );
      mutate();
    } catch (problem) {
      toast.error("Could not save pipeline settings", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <h2 className="text-[15px] font-semibold">Pipeline defaults</h2>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          Global defaults for new bids. Each bid can override autopilot at creation.
        </p>
      </div>

      {error && (
        <FetchError
          title="Could not load pipeline settings"
          error={error}
          onRetry={() => mutate()}
          compact
        />
      )}
      {isLoading && !data && !error && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Loading…
        </p>
      )}
      {data && (
        <div className="flex flex-wrap items-start justify-between gap-4 px-4 py-4">
          <div className="max-w-[520px]">
            <p className="text-[13px] font-medium">Autopilot default for new bids</p>
            <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-2)" }}>
              {data.note ??
                "When enabled, uploading a drawing runs Phase 0–6 in one pass. Nothing is ever sent."}
            </p>
            {data.updatedBy && (
              <p className="mt-2 text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                Last changed by {data.updatedBy}
                {data.updatedAt ? ` · ${new Date(data.updatedAt).toLocaleString()}` : ""}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={toggleAutopilot}
            disabled={busy}
            aria-pressed={data.autopilotDefault}
            className="rounded-md px-4 py-2 text-[12px] font-semibold disabled:opacity-50"
            style={{
              background: data.autopilotDefault ? "var(--app-accent)" : "var(--app-panel-2)",
              color: data.autopilotDefault ? "#fff" : "var(--app-tx-2)",
              border: `1px solid ${data.autopilotDefault ? "var(--app-accent-line)" : "var(--app-line)"}`,
            }}
          >
            {busy ? "Saving…" : data.autopilotDefault ? "Autopilot on" : "Autopilot off"}
          </button>
        </div>
      )}
    </section>
  );
}

export function IntegrationsPanel() {
  const { data, error, isLoading } = useSWR<IntegrationsResponse>(
    endpoints.integrations(),
    proxyFetcher,
  );
  const p21 = data?.p21;

  return (
    <section
      className="rounded-xl"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
        <h2 className="text-[15px] font-semibold">Integrations</h2>
        <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-3)" }}>
          External systems that feed Path 1 pricing and cost freshness.
        </p>
      </div>

      {error && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-neg)" }}>
          Could not load integration status: {errorMessage(error)}
        </p>
      )}
      {isLoading && !data && !error && (
        <p className="px-4 py-6 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Loading…
        </p>
      )}

      {p21 && (
        <div className="px-4 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="max-w-[560px]">
              <p className="text-[13px] font-semibold">{p21.title}</p>
              <p className="mt-1 text-[12px]" style={{ color: "var(--app-tx-2)" }}>
                {p21.summary}
              </p>
            </div>
            <span
              className="rounded-md px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.05em]"
              style={{
                background: p21.connected ? "var(--app-ok-soft)" : "var(--app-warn-soft)",
                color: p21.connected ? "var(--app-ok)" : "var(--app-warn)",
                border: `1px solid ${p21.connected ? "var(--app-ok-line)" : "var(--app-warn-line)"}`,
              }}
            >
              {p21.connected ? "Connected" : "Deferred (NR-10)"}
            </span>
          </div>
          <p
            className="mt-3 rounded-md px-3 py-2 text-[12px] leading-relaxed"
            style={{
              background: "var(--app-panel-2)",
              border: "1px solid var(--app-line)",
              color: "var(--app-tx-2)",
            }}
          >
            {p21.note}
          </p>
          {!p21.connected && p21.fallbacks && p21.fallbacks.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
              {p21.fallbacks.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
