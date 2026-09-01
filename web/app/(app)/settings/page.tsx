import { ClaudeSettingsClient } from "@/components/settings/claude-settings";
import { AdminSettingsClient } from "@/components/settings/admin-settings-client";
import { IntegrationsPanel } from "@/components/settings/admin-panels";
import { PageHeader } from "@/components/shell/page-header";
import { auth } from "@/auth";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const session = await auth();
  const role = session?.user?.role ?? "estimator";
  const isAdmin = role === "admin";

  return (
    <>
      <PageHeader crumbs={[{ label: "Workspace", href: "/dashboard" }, { label: "Settings" }]} />
      <div className="flex flex-col gap-4 p-4">
        {isAdmin ? (
          <>
            <section
              className="rounded-xl px-4 py-3"
              style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
            >
              <h2 className="text-[15px] font-semibold">Administration</h2>
              <p className="mt-1 text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
                Configure the AI provider, pipeline defaults, user accounts, and review the audit log.
              </p>
            </section>
            <ClaudeSettingsClient />
            <AdminSettingsClient />
          </>
        ) : (
          <>
            <IntegrationsPanel />
            <section
              className="rounded-xl p-6"
              style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
            >
              <h2 className="text-[15px] font-semibold">Automation status</h2>
              <p className="mt-2 text-[13px] leading-relaxed" style={{ color: "var(--app-tx-2)" }}>
                Your administrator configures the AI provider that reads bid documents and prices lines.
                If automatic reads fail, add lines by hand or ask your admin to check Settings.
              </p>
              <p className="mt-3 text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
                Provider configuration and user administration are limited to administrators.
              </p>
            </section>
          </>
        )}
      </div>
    </>
  );
}
