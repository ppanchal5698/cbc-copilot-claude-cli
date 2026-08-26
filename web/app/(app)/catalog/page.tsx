import { CatalogClient } from "@/components/catalog/catalog-client";
import { PageHeader } from "@/components/shell/page-header";

export const dynamic = "force-dynamic";

export default function CatalogPage() {
  return (
    <>
      <PageHeader crumbs={[{ label: "Workspace", href: "/dashboard" }, { label: "Product catalog" }]} />
      <CatalogClient />
    </>
  );
}
