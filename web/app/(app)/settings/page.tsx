import { ClaudeSettingsClient } from "@/components/settings/claude-settings";
import { AdminSettingsClient } from "@/components/settings/admin-settings-client";
import { PageHeader } from "@/components/shell/page-header";
import { auth } from "@/auth";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const session = await auth();
  const role = (session?.user as { role?: string } | undefined)?.role ?? "estimator";
  const isAdmin = role === "admin" || role === "purchasing";

  return (
    <>
      <PageHeader crumbs={[{ label: "Workspace", href: "/dashboard" }, { label: "Settings" }]} />
      <div className="flex flex-col gap-4 p-4">
        <ClaudeSettingsClient />
        {isAdmin && <AdminSettingsClient />}
      </div>
    </>
  );
}
