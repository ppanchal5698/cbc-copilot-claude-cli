"use client";

import { AuditLogPanel, UsersAdminPanel } from "@/components/settings/admin-panels";

export function AdminSettingsClient() {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <UsersAdminPanel />
      <AuditLogPanel />
    </div>
  );
}
