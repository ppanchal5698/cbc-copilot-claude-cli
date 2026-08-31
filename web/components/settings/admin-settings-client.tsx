"use client";

import {
  AuditLogPanel,
  PipelineSettingsPanel,
  UsersAdminPanel,
} from "@/components/settings/admin-panels";

export function AdminSettingsClient() {
  return (
    <div className="flex flex-col gap-4">
      <PipelineSettingsPanel />
      <div className="grid gap-4 xl:grid-cols-2">
        <UsersAdminPanel />
        <AuditLogPanel />
      </div>
    </div>
  );
}
