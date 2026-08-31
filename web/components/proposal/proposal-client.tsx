"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  ArrowLeft,
  DownloadSimple,
  CheckCircle,
  WarningCircle,
  Circle,
  SealCheck,
  Copy,
} from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import { JobFailedBanner } from "@/components/jobs/job-failed-banner";
import { useUiState } from "@/components/shell/ui-state";
import { formatMoney } from "@/lib/format";
import type { EmailDraft, HandOffResult, Job, ProposalResponse } from "@/lib/types";

import { endpoints } from "@/lib/endpoints";
import { errorMessage, proxyFetch, proxyFetcher, proxyMutate } from "@/lib/proxy-fetcher";

const MARKUPS = [
  { value: 0, label: "None" },
  { value: 0.02, label: "2%" },
  { value: 0.05, label: "5%" },
];

export function ProposalClient({
  code,
  initialJob,
}: {
  code: string;
  initialJob?: Job | null;
}) {
  const { userRole } = useUiState();
  const [busy, setBusy] = useState(false);
  const [handOff, setHandOff] = useState<HandOffResult | null>(null);

  const { data: jobData } = useSWR<{ jobs: Job[] }>(
    `/api/proxy/jobs?project=${code}&limit=1`,
    proxyFetcher,
    {
      refreshInterval: (latest) => {
        const current = latest?.jobs?.[0] ?? initialJob;
        return current?.status === "running" || current?.status === "queued" ? 4000 : 0;
      },
      fallbackData: initialJob ? { jobs: [initialJob] } : undefined,
    },
  );
  const job = jobData?.jobs?.[0] ?? null;

  const { data, error, mutate } = useSWR<ProposalResponse>(
    `/api/proxy/projects/${code}/proposal`,
    proxyFetcher,
  );

  // A failed fetch used to fall into the same branch as a pending one, so any
  // API problem showed "Building the proposal…" for ever with no way out.
  if (error) {
    return (
      <main className="grid flex-1 place-items-center p-6">
        <div className="grid max-w-[440px] justify-items-center gap-2 text-center">
          <WarningCircle size={24} weight="duotone" style={{ color: "var(--app-neg)" }} />
          <span className="text-[14px] font-semibold">Could not build the proposal</span>
          <span className="text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
            {errorMessage(error)}
          </span>
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => mutate()}
              className="rounded-md px-3 py-1.5 text-[12.5px] font-semibold"
              style={{ background: "var(--app-accent)", color: "#fff" }}
            >
              Try again
            </button>
            <a
              href={`/bids/${code}/quote`}
              className="rounded-md px-3 py-1.5 text-[12.5px] no-underline"
              style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
            >
              Back to the quote
            </a>
          </div>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="grid flex-1 place-items-center">
        <span className="text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
          Building the proposal…
        </span>
      </main>
    );
  }

  const { proposal, project, sections, totals, readiness } = data;

  async function setMarkup(markup: number) {
    try {
      await proxyMutate(`/api/proxy/projects/${code}/proposal`, {
        method: "PATCH",
        body: { markup },
      });
      mutate();
    } catch (problem) {
      toast.error("Could not change the markup", { description: errorMessage(problem) });
    }
  }

  /** Try the server renderer; fall back to the browser's own print-to-PDF. */
  async function downloadPdf() {
    const response = await proxyFetch(endpoints.proposalPdf(code));

    if (response.ok) {
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${code}-proposal.pdf`;
      // Firefox and Safari ignore a click on a link that is not in the document,
      // and revoking the URL in the same tick cancels the download that did
      // start. Attach, click, then clean up once the browser has taken it.
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      setTimeout(() => {
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }, 0);
      return;
    }

    const body = await response.json().catch(() => ({ detail: response.statusText }));
    toast.info("Printing from the browser instead", {
      description: "No local PDF renderer is installed, so the print dialog opens instead.",
    });
    console.warn("PDF renderer unavailable:", body.detail);
    window.open(`/api/proxy/projects/${code}/proposal/render?autoprint=1`, "_blank");
  }

  async function markComplete() {
    setBusy(true);
    try {
      const result = await proxyMutate<HandOffResult>(
        `/api/proxy/projects/${code}/proposal/complete`,
        { body: {} },
      );
      setHandOff(result);
      toast.success("Signed off", { description: result.message });
      mutate();
    } catch (problem) {
      toast.error("Could not record the sign-off", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  /** Copy the drafted body. The estimator sends it from their own mail client. */
  async function copyBody() {
    let draft: EmailDraft;
    try {
      draft = await proxyFetcher<EmailDraft>(`/api/proxy/projects/${code}/proposal/email-draft`);
    } catch (problem) {
      toast.error("Could not build the email body", { description: errorMessage(problem) });
      return;
    }
    const text = `To: ${draft.to ?? "(no initiator recorded)"}
Subject: ${draft.subject}

${draft.body}`;
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Email body copied", { description: draft.note ?? undefined });
    } catch {
      toast.error("Clipboard blocked", { description: "Select the text in the printable view instead." });
    }
  }

  async function rebuildProposal() {
    setBusy(true);
    try {
      await proxyMutate(`/api/proxy/projects/${code}/quote/continue-to-proposal`);
      toast.success("Proposal rebuild queued");
      mutate();
    } catch (problem) {
      toast.error("Could not queue the proposal", { description: errorMessage(problem) });
    } finally {
      setBusy(false);
    }
  }

  const signoff = [
    {
      state: proposal.signoff.some((entry) => entry.role === "estimator") ? "done" : "todo",
      title: "Estimator review complete",
      detail: proposal.signoff[0]
        ? `${proposal.signoff[0].by} · ${new Date(proposal.signoff[0].at).toLocaleDateString()}`
        : "Not yet signed off",
    },
    {
      state: readiness.flaggedLineItems > 0 ? "warn" : "done",
      title:
        readiness.flaggedLineItems > 0
          ? `${readiness.flaggedLineItems} item${readiness.flaggedLineItems === 1 ? "" : "s"} still flagged`
          : "Every line checked",
      detail:
        readiness.flaggedLineItems > 0
          ? "They price at the assumed value"
          : "No open extraction flags",
    },
    {
      state: readiness.unpricedQuoteLines > 0 ? "warn" : "done",
      title:
        readiness.unpricedQuoteLines > 0
          ? `${readiness.unpricedQuoteLines} line${readiness.unpricedQuoteLines === 1 ? "" : "s"} unpriced`
          : "Everything priced",
      detail:
        readiness.unpricedQuoteLines > 0
          ? "Manual or awaiting a vendor quote"
          : "No manual gaps left",
    },
    { state: "todo", title: "Awaiting sales sign-off", detail: project.initiator ?? "sales representative" },
  ];

  return (
    <>
      <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 xl:flex-row xl:items-start">
        <section className="isolate z-0 min-h-0 min-w-0 flex-1">
          {job?.status === "failed" && job && (
            <div className="mx-auto mb-3 max-w-[820px]">
              <JobFailedBanner
                job={job}
                role={userRole}
                stage="proposal"
                onAction={(action) => {
                  if (action.label === "Re-build proposal") rebuildProposal();
                  else if (action.label === "Notify your admin") {
                    toast.message("Ask your administrator to configure the AI provider in Settings.");
                  }
                }}
              />
            </div>
          )}

          {handOff && (
            <div
              className="anim-fadein mx-auto mb-3 flex max-w-[820px] items-start gap-3 rounded-xl px-4 py-3"
              style={{
                background: "var(--app-pos-soft)",
                border: "1px solid var(--app-pos)",
                color: "var(--app-pos)",
              }}
            >
              <SealCheck size={18} weight="duotone" />
              <span className="flex flex-1 flex-col leading-tight">
                <span className="text-[13px] font-semibold">
                  {handOff.handedOffTo
                    ? `Handed to ${handOff.handedOffTo}`
                    : "Signed off — nobody to route to"}
                </span>
                <span className="text-[11.5px]">
                  {handOff.message} The draft body is at {handOff.draftPath}.
                </span>
              </span>
              <button
                onClick={copyBody}
                className="flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11.5px]"
                style={{ border: "1px solid var(--app-pos)", color: "var(--app-pos)" }}
              >
                <Copy size={13} weight="duotone" />
                Copy the email body
              </button>
            </div>
          )}

          <article
            className="mx-auto max-w-[820px] overflow-x-auto rounded-xl px-5 py-6 sm:px-10 sm:py-9"
            style={{ background: "#ffffff", color: "#15151f", boxShadow: "var(--app-sh-2)" }}
          >
            <header className="flex items-start justify-between">
              <div>
                <h1 className="text-[26px] font-semibold">Proposal</h1>
                <p className="mt-2.5 text-[11.5px] leading-relaxed" style={{ color: "#55556b" }}>
                  CBC Construction Building Components — A Division of The Hamilton Parker Company
                  <br />
                  1865 Leonard Ave. Columbus, OH 43219 · Phone (614) 358-7800
                </p>
              </div>
              <table className="text-[11.5px]">
                <tbody>
                  <tr>
                    <td className="pr-4 text-right" style={{ color: "#55556b" }}>
                      Proposal No.
                    </td>
                    <td className="tnum font-semibold">{proposal.proposalNo}</td>
                  </tr>
                  <tr>
                    <td className="pr-4 text-right" style={{ color: "#55556b" }}>
                      Date
                    </td>
                    <td className="tnum font-semibold">{proposal.date}</td>
                  </tr>
                  <tr>
                    <td className="pr-4 text-right" style={{ color: "#55556b" }}>
                      Valid
                    </td>
                    <td className="tnum font-semibold">{proposal.validityDays} days</td>
                  </tr>
                  <tr>
                    <td className="pr-4 text-right" style={{ color: "#55556b" }}>
                      Order #
                    </td>
                    <td className="tnum font-semibold">—</td>
                  </tr>
                </tbody>
              </table>
            </header>

            <div
              className="mt-6 grid grid-cols-3 gap-4 rounded border p-3.5 text-[11.5px]"
              style={{ borderColor: "#d6d9de" }}
            >
              <div>
                <span className="block" style={{ color: "#55556b" }}>
                  Customer
                </span>
                <span className="font-semibold">{project.gc ?? "—"}</span>
              </div>
              <div>
                <span className="block" style={{ color: "#55556b" }}>
                  Requested by
                </span>
                <span className="font-semibold">{project.initiator ?? "—"}</span>
              </div>
              <div>
                <span className="block" style={{ color: "#55556b" }}>
                  Estimator
                </span>
                <span className="font-semibold">
                  {proposal.estimator?.name ?? "CBC Estimating"}
                </span>
              </div>
              <div className="col-span-2">
                <span className="block" style={{ color: "#55556b" }}>
                  Job name
                </span>
                <span className="font-semibold">{project.jobName ?? project.name}</span>
              </div>
              <div>
                <span className="block" style={{ color: "#55556b" }}>
                  Location
                </span>
                <span className="font-semibold">{project.location ?? "—"}</span>
              </div>
            </div>

            <p className="mt-5 text-[10px] leading-relaxed" style={{ color: "#55556b" }}>
              This quote is conditioned upon the use of HAMILTON PARKER CO. purchase order as the
              parties contract. This quote is only good for {proposal.validityDays} days from the
              date of this quote. All special order materials not picked up within 30 days are
              subject to invoicing unless other arrangements have been made.
            </p>

            {sections.map((section) => (
              <section key={section.key} className="mt-6">
                <div
                  className="flex items-baseline justify-between border-b pb-1.5"
                  style={{ borderColor: "#15151f" }}
                >
                  <h2 className="text-[12px] font-bold uppercase tracking-[0.05em]">
                    {section.title}
                  </h2>
                  <span className="tnum text-[12.5px] font-bold">
                    ${formatMoney(section.subtotal)}
                  </span>
                </div>

                <table className="mt-2 w-full text-[10.5px]">
                  <thead>
                    <tr style={{ color: "#55556b" }}>
                      <th className="w-[140px] py-1 text-left font-medium">PART</th>
                      <th className="w-[44px] py-1 text-left font-medium">QTY</th>
                      <th className="w-[40px] py-1 text-left font-medium">UOM</th>
                      <th className="py-1 text-left font-medium">DESCRIPTION</th>
                      <th className="w-[80px] py-1 text-right font-medium">UNIT PRICE</th>
                      <th className="w-[86px] py-1 text-right font-medium">EXT. PRICE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {section.lines.map((line, index) => (
                      <tr key={`${line.part}-${index}`} className="border-t" style={{ borderColor: "#eceef1" }}>
                        <td className="py-1 font-medium">{line.part ?? "—"}</td>
                        <td className="tnum py-1" style={{ color: "#5b5bd6" }}>
                          {line.qty}
                        </td>
                        <td className="py-1">{line.uom}</td>
                        <td className="py-1" style={{ color: "#5b5bd6" }}>
                          {line.description}
                        </td>
                        <td className="tnum py-1 text-right">
                          {line.unitPrice === null ? (
                            <span style={{ color: "#b45309" }}>{line.priceStatus ?? "MANUAL"}</span>
                          ) : (
                            `$${formatMoney(line.unitPrice)}`
                          )}
                        </td>
                        <td className="tnum py-1 text-right font-medium">
                          {line.extPrice === null ? "—" : `$${formatMoney(line.extPrice)}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ))}

            <div className="mt-8 flex justify-end pb-12">
              <table className="w-[300px] text-[11.5px]">
                <tbody>
                  <tr>
                    <td className="py-1" style={{ color: "#55556b" }}>
                      Subtotal
                    </td>
                    <td className="tnum py-1 text-right">${formatMoney(totals.subtotal)}</td>
                  </tr>
                  <tr>
                    <td className="py-1" style={{ color: "#55556b" }}>
                      Freight
                    </td>
                    <td className="tnum py-1 text-right">
                      {totals.freight ? `$${formatMoney(totals.freight)}` : "TBD"}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-1" style={{ color: "#55556b" }}>
                      Sales tax {totals.taxJurisdiction ? `(${totals.taxJurisdiction})` : ""}
                    </td>
                    <td className="tnum py-1 text-right">
                      {totals.taxJurisdiction ? (
                        `$${formatMoney(totals.tax)}`
                      ) : (
                        <span style={{ color: "#b45309" }}>UNRESOLVED</span>
                      )}
                    </td>
                  </tr>
                  <tr className="border-t-2" style={{ borderColor: "#0f3d2e" }}>
                    <td className="pt-2 text-[14px] font-bold" style={{ color: "#0f3d2e" }}>
                      Grand total
                    </td>
                    <td
                      className="tnum pt-2 text-right text-[17px] font-bold"
                      style={{ color: "#0f3d2e" }}
                    >
                      ${formatMoney(totals.grandTotal)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <footer className="mt-8 border-t pt-4 text-[10.5px]" style={{ borderColor: "#d6d9de", color: "#55556b" }}>
              <p className="font-semibold" style={{ color: "#15151f" }}>
                Terms
              </p>
              <ul className="mt-1 list-disc pl-4">
                <li>Hamilton Parker purchase order required.</li>
                <li>Supply-only material. Installation labor is not included.</li>
                <li>Freight is handled when a quote becomes a job.</li>
                <li>Sales tax is charged for Ohio and Kentucky only.</li>
              </ul>
            </footer>
          </article>
        </section>

        <aside
          className="z-10 flex shrink-0 flex-col gap-3 xl:sticky xl:top-4 xl:w-[320px] xl:self-start"
          style={{ background: "var(--app-bg)" }}
        >
          <div
            className="rounded-xl p-4"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            <span
              className="block text-[10.5px] uppercase tracking-[0.07em]"
              style={{ color: "var(--app-tx-3)" }}
            >
              Proposal settings
            </span>
            <span className="mt-3 block text-[12.5px] font-semibold">Presentation markup</span>
            <div className="mt-2 flex gap-1">
              {MARKUPS.map((option) => {
                const active = Math.abs(proposal.markup - option.value) < 0.0001;
                return (
                  <button
                    key={option.label}
                    onClick={() => setMarkup(option.value)}
                    className="flex-1 rounded-md py-1.5 text-[12px]"
                    style={{
                      background: active ? "var(--app-panel-2)" : "transparent",
                      color: active ? "var(--app-tx)" : "var(--app-tx-2)",
                      border: `1px solid ${active ? "var(--app-line)" : "transparent"}`,
                    }}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-[11px]" style={{ color: "var(--app-tx-3)" }}>
              The customer sees the sell price straight off the quote grid.
            </p>
          </div>

          <div
            className="rounded-xl p-4"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            <span
              className="block text-[10.5px] uppercase tracking-[0.07em]"
              style={{ color: "var(--app-tx-3)" }}
            >
              Sign-off
            </span>
            <div className="mt-3 flex flex-col gap-3">
              {signoff.map((entry) => (
                <div key={entry.title} className="flex gap-2.5">
                  {entry.state === "done" ? (
                    <CheckCircle size={15} weight="fill" style={{ color: "var(--app-accent)" }} />
                  ) : entry.state === "warn" ? (
                    <WarningCircle size={15} weight="fill" style={{ color: "var(--app-neg)" }} />
                  ) : (
                    <Circle size={15} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
                  )}
                  <span className="flex flex-col leading-tight">
                    <span className="text-[12.5px]">{entry.title}</span>
                    <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
                      {entry.detail}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div
            className="rounded-xl p-4"
            style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
          >
            <span
              className="block text-[10.5px] uppercase tracking-[0.07em]"
              style={{ color: "var(--app-tx-3)" }}
            >
              Exclusions on the sheet
            </span>
            <ul className="mt-2.5 flex flex-col gap-2">
              {proposal.exclusions.map((exclusion) => (
                <li key={exclusion} className="text-[11.5px]" style={{ color: "var(--app-tx-2)" }}>
                  {exclusion}
                </li>
              ))}
            </ul>
          </div>

          <button
            onClick={markComplete}
            disabled={busy}
            className="flex items-center justify-center gap-2 rounded-lg py-3 text-[13px] font-semibold disabled:opacity-60"
            style={{ background: "var(--app-accent)", color: "#fff" }}
          >
            {project.initiator
              ? `Mark complete and route to ${project.initiator}`
              : "Mark complete and hand to sales"}
          </button>
          <p className="text-center text-[11px]" style={{ color: "var(--app-tx-3)" }}>
            This records your sign-off and puts the bid in their queue. It does not send anything.
          </p>
        </aside>
      </main>

      <footer
        className="flex shrink-0 flex-wrap items-center gap-3 border-t px-5 py-3"
        style={{ borderColor: "var(--app-line)", background: "var(--app-bg)" }}
      >
        <a
          href={`/bids/${code}/quote`}
          className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px] no-underline"
          style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
        >
          <ArrowLeft size={14} weight="bold" />
          Back
        </a>
        <span
          className="min-w-[200px] flex-1 text-[12.5px]"
          style={{ color: "var(--app-tx-2)" }}
        >
          The customer sees the marked-up total only. Nothing is sent from here.
        </span>
        <a
          href={`/api/proxy/projects/${code}/proposal/render`}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12.5px] no-underline"
          style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
        >
          Open printable view
        </a>
        <button
          onClick={downloadPdf}
          className="flex items-center gap-1.5 rounded-md px-4 py-2 text-[12.5px] font-semibold"
          style={{ background: "var(--app-accent)", color: "#fff" }}
        >
          <DownloadSimple size={14} weight="bold" />
          Download PDF
        </button>
      </footer>
    </>
  );
}
