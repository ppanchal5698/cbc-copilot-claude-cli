import { ClaudeSettingsClient } from "@/components/settings/claude-settings";
import { PageHeader } from "@/components/shell/page-header";

export const dynamic = "force-dynamic";

export default function SettingsPage() {
  return (
    <>
      <PageHeader crumbs={[{ label: "Workspace", href: "/dashboard" }, { label: "Settings" }]} />
      <ClaudeSettingsClient />
    </>
  );
}
