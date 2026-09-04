import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";

import { DeleteBidButton } from "@/components/bids/delete-bid-button";
import { UploadPanel } from "@/components/intake/upload-panel";
import { VersionsPanel } from "@/components/intake/versions-panel";
import { PageHeader } from "@/components/shell/page-header";
import { runPillFor } from "@/lib/run-pill";
import { StageBar } from "@/components/shell/stage-bar";
import { ApiError, api } from "@/lib/api";
import { auth } from "@/auth";
import type { BidDocument, Job, Project } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function IntakePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const session = await auth();
  const role = session?.user?.role ?? "estimator";

  let project: Project;
  try {
    project = await api.get<Project>(`/api/projects/${code}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const [documents, jobs] = await Promise.all([
    api
      .get<{ documents: BidDocument[] }>(`/api/projects/${code}/documents`)
      .then((r) => r.documents),
    api
      .get<{ jobs: Job[] }>(`/api/jobs?project=${code}&limit=1`)
      .then((r) => r.jobs),
  ]);

  const record: [string, string | null | undefined][] = [
    ["Number", project.code],
    ["Brand", project.brand],
    ["Job name", project.jobName ?? project.name],
    ["Project number", project.projectNumber],
    ["Location", project.location],
    ["State", project.state],
    ["Architect", project.architect],
    ["General contractor", project.gc],
    ["Requested by", project.initiator],
    ["Bid due", project.bidDue ? new Date(project.bidDue).toLocaleDateString() : null],
  ];

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Workspace", href: "/dashboard" },
          { label: `${project.code} · Intake` },
        ]}
        runPill={runPillFor(jobs[0], project.counts.total, project.phase)}
        reviewCount={project.counts.needsLook}
        code={project.code}
      />
      <StageBar project={project} current="intake" />

      <main id="main-content" className="min-h-0 flex-1 overflow-auto p-4">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">
          <div className="flex flex-col gap-4">
            <UploadPanel code={project.code} initialDocuments={documents} />
            <VersionsPanel code={project.code} />
          </div>

          <aside className="h-fit overflow-hidden rounded-xl bg-panel border border-subtle shadow-sm">
            <div className="border-b border-subtle px-4 py-3.5">
              <span className="text-[15px] font-semibold text-tx-primary">Job record</span>
            </div>
            <div className="px-4 py-2">
              {record.map(([label, value]) => (
                <div
                  key={label}
                  className="grid grid-cols-[110px_1fr] items-baseline gap-3 border-b border-subtle py-2 last:border-b-0"
                >
                  <span className="text-[11.5px] text-tx-muted">{label}</span>
                  <span
                    className={`text-right text-[12.5px] ${
                      value ? "text-tx-primary" : "text-tx-muted"
                    }`}
                  >
                    {value ?? "not recorded"}
                  </span>
                </div>
              ))}
            </div>
            {!project.state && (
              <p className="mx-4 mb-4 rounded-md border border-status-warning/30 bg-status-warning-soft px-3 py-2 text-[11.5px] text-status-warning">
                No ship-to state recorded, so sales tax stays unresolved on the quote. Tax applies
                to Ohio and Kentucky only.
              </p>
            )}
            <DeleteBidButton
              code={project.code}
              name={project.jobName ?? project.name}
              role={role}
            />
          </aside>
        </div>
      </main>

      <footer className="flex shrink-0 items-center gap-3 border-t border-subtle bg-background px-5 py-3">
        <span className="flex-1 text-[12.5px] text-tx-secondary">
          {documents.length === 0
            ? "Add the plan set to start. Claude reads it as soon as it lands."
            : `${documents.length} document${documents.length === 1 ? "" : "s"} on file.`}
        </span>
        <Link
          href={`/bids/${project.code}/extraction`}
          className="flex items-center gap-1.5 rounded-md bg-brand-primary px-4 py-2 text-[12.5px] font-semibold text-white no-underline hover:bg-brand-primary/90"
        >
          Go to Extraction & entry
          <ArrowRight size={14} weight="bold" />
        </Link>
      </footer>
    </>
  );
}
