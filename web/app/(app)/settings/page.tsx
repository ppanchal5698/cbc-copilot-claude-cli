import { ClaudeSettingsClient } from "@/components/settings/claude-settings";
import { AdminSettingsClient } from "@/components/settings/admin-settings-client";
import { PageHeader } from "@/components/shell/page-header";
import { auth } from "@/auth";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const session = await auth();
  const role = session?.user?.role ?? "estimator";
  const isAdmin = role === "admin" || role === "purchasing";

  return (
    <>
      <PageHeader crumbs={[{ label: "Workspace", href: "/dashboard" }, { label: "Settings" }]} />
      <div className="flex flex-col gap-4 p-4">
        {isAdmin ? (
          <>
            <ClaudeSettingsClient />
            <AdminSettingsClient />
          </>
        ) : (
          <section
            className="rounded-xl p-6"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            <h2 className="text-[15px] font-semibold">Settings</h2>
            <p className="mt-2 text-[13px]" style={{ color: "var(--app-tx-2)" }}>
              Provider configuration and user administration are limited to admin and purchasing
              roles. Contact your administrator if you need access.
            </p>
          </section>
        )}
      </div>
    </>
  );
}
