"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { FilePdf, Minus, Plus, X, ArrowsOut } from "@phosphor-icons/react/dist/ssr";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { documentUrl } from "@/lib/proxy-fetcher";
import type { BidDocument, LineItem } from "@/lib/types";

// The version query busts a cached worker from a previous pdfjs; a mismatched
// worker makes the viewer refuse to open any file.
pdfjs.GlobalWorkerOptions.workerSrc = `/pdf.worker.min.mjs?v=${pdfjs.version}`;

const BASE_PAGE_WIDTH = 520;
const MIN_ZOOM = 0.4;
const MAX_ZOOM = 10;
/** How much of the viewport the highlight should fill when auto-zooming. */
const FIT_RATIO = 0.88;

function zoomToFitHighlight(
  bbox: number[],
  pageSize: { width: number; height: number },
  viewportWidth: number,
  viewportHeight: number,
): number {
  const [x0, y0, x1, y1] = bbox;
  const bboxWidth = Math.max(x1 - x0, 1);
  const bboxHeight = Math.max(y1 - y0, 1);
  const scaleAtZoom1 = BASE_PAGE_WIDTH / pageSize.width;
  const widthAtZoom1 = bboxWidth * scaleAtZoom1;
  const heightAtZoom1 = bboxHeight * scaleAtZoom1;

  const zoomW = (viewportWidth * FIT_RATIO) / widthAtZoom1;
  const zoomH = (viewportHeight * FIT_RATIO) / heightAtZoom1;

  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.min(zoomW, zoomH)));
}

/**
 * The real drawing, with a highlight box over the spot a value was read from.
 *
 * This deliberately renders the source PDF rather than a re-rendering of the
 * extraction: checking Claude's output against Claude's output verifies nothing.
 * The box comes from `evidence.bbox`, in PDF points, scaled by the rendered
 * width over `evidence.pageSize.width`.
 */
export function SheetViewer({
  code,
  documents,
  selected,
  onClose,
}: {
  code: string;
  documents: BidDocument[];
  selected: LineItem | null;
  onClose: () => void;
}) {
  const [activeDocId, setActiveDocId] = useState(documents[0]?.id ?? "");
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [renderedWidth, setRenderedWidth] = useState(0);
  // Keyed by document: an unreadable PDF must not blank the viewer for the
  // others. Previously the failure branch replaced <Document> entirely, so the
  // onLoadSuccess that would have cleared it could never fire again.
  const [failures, setFailures] = useState<Record<string, string>>({});
  const frameRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);

  const evidence = selected?.evidence;
  const bbox = evidence?.bbox ?? null;
  const pageSize = evidence?.pageSize ?? null;

  const fitZoomToHighlight = useCallback(() => {
    if (!bbox || !pageSize || !frameRef.current) return;
    const pad = 24;
    const vw = Math.max(frameRef.current.clientWidth - pad, 1);
    const vh = Math.max(frameRef.current.clientHeight - pad, 1);
    setZoom(zoomToFitHighlight(bbox, pageSize, vw, vh));
  }, [bbox, pageSize]);

  // Follow the selected line to its page and document. Derived from which line
  // is selected rather than pushed from an effect, so the first render after a
  // selection already shows the right page.
  const [followed, setFollowed] = useState<string | null>(null);
  const selectionKey = selected ? `${selected.id}:${evidence?.sourcePage ?? ""}` : null;
  if (selectionKey && followed !== selectionKey) {
    setFollowed(selectionKey);
    if (evidence?.sourcePage) {
      setPageNumber(evidence.sourcePage);
      if (evidence.sourceFile) {
        const match = documents.find((doc) => evidence.sourceFile?.includes(doc.filename));
        if (match) setActiveDocId(match.id);
      }
    }
    if (!bbox || !pageSize) setZoom(1);
  }

  // Zoom in on the linked region whenever a line item with a bbox is selected.
  useEffect(() => {
    if (!bbox || !pageSize) return;
    // Wait for layout so viewport measurements reflect the open pane.
    let inner = 0;
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => fitZoomToHighlight());
    });
    return () => {
      cancelAnimationFrame(outer);
      cancelAnimationFrame(inner);
    };
  }, [selected?.id, bbox, pageSize, fitZoomToHighlight]);

  // Bring the highlight into view once it exists.
  useEffect(() => {
    if (!highlightRef.current) return;
    highlightRef.current.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
  }, [bbox, renderedWidth, pageNumber, zoom]);

  const activeDoc = documents.find((doc) => doc.id === activeDocId) ?? documents[0];
  const failure = activeDoc ? failures[activeDoc.id] : undefined;

  const fileUrl = useMemo(
    () => (activeDoc ? documentUrl(code, activeDoc.id) : null),
    [code, activeDoc],
  );

  /**
   * The rendered canvas is the source of truth for scale.
   *
   * react-pdf's onRenderSuccess hands back a page proxy, not a width, so
   * measuring the canvas is both simpler and correct at any zoom.
   */
  const measurePage = useCallback(() => {
    const canvas = pageRef.current?.querySelector("canvas");
    if (canvas) setRenderedWidth(canvas.getBoundingClientRect().width);
  }, []);

  // Re-measure when the pane or zoom changes.
  useEffect(() => {
    const node = pageRef.current;
    if (!node) return;
    const observer = new ResizeObserver(measurePage);
    observer.observe(node);
    return () => observer.disconnect();
  }, [measurePage, activeDocId]);

  // The highlight only makes sense on the page the value was read from.
  const highlight = useMemo(() => {
    if (!bbox || !pageSize || !renderedWidth) return null;
    if (evidence?.sourcePage !== pageNumber) return null;

    const scale = renderedWidth / pageSize.width;
    const [x0, y0, x1, y1] = bbox;
    const padding = 3;

    return {
      left: x0 * scale - padding,
      top: y0 * scale - padding,
      width: (x1 - x0) * scale + padding * 2,
      height: (y1 - y0) * scale + padding * 2,
    };
  }, [bbox, pageSize, evidence?.sourcePage, renderedWidth, pageNumber]);

  if (!activeDoc || !fileUrl) {
    return (
      <aside
        className="flex w-full shrink-0 flex-col rounded-xl xl:w-[clamp(380px,34vw,560px)]"
        style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
      >
        <div className="grid flex-1 place-items-center px-6 text-center">
          <span className="text-[12.5px]" style={{ color: "var(--app-tx-2)" }}>
            No bid documents uploaded yet.
          </span>
        </div>
      </aside>
    );
  }

  return (
    <aside
      className="anim-fadein flex h-[420px] w-full shrink-0 flex-col overflow-hidden rounded-xl xl:h-auto xl:w-[clamp(380px,34vw,560px)]"
      style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
    >
      <div
        className="flex items-center gap-2.5 border-b px-4 py-3"
        style={{ borderColor: "var(--app-line)" }}
      >
        <FilePdf size={18} weight="duotone" style={{ color: "#22d3ee" }} />
        <span className="flex min-w-0 flex-1 flex-col leading-tight">
          <span className="truncate text-[13px] font-semibold">{activeDoc.filename}</span>
          <span className="text-[11px]" style={{ color: "var(--app-tx-3)" }}>
            page {pageNumber} of {pageCount || activeDoc.pages || "?"}
            {evidence?.sheet ? ` · ${evidence.sheet}` : ""}
          </span>
        </span>
        <button onClick={onClose} style={{ color: "var(--app-tx-3)" }} aria-label="Hide the sheet">
          <X size={15} weight="bold" />
        </button>
      </div>

      <div
        className="flex items-center gap-1.5 border-b px-3 py-2"
        style={{ borderColor: "var(--app-line)" }}
      >
        <div className="flex gap-1 overflow-x-auto">
          {documents.map((doc) => (
            <button
              key={doc.id}
              onClick={() => {
                setActiveDocId(doc.id);
                setPageNumber(1);
              }}
              aria-label={`Show ${doc.filename}`}
              aria-current={doc.id === activeDocId ? "page" : undefined}
              className="whitespace-nowrap rounded-md px-2.5 py-1 text-[11.5px]"
              style={{
                background: doc.id === activeDocId ? "var(--app-accent-soft)" : "transparent",
                color: doc.id === activeDocId ? "var(--app-accent)" : "var(--app-tx-2)",
                border: `1px solid ${doc.id === activeDocId ? "var(--app-accent-line)" : "transparent"}`,
              }}
            >
              {doc.filename.replace(/\.pdf$/i, "").slice(0, 18)}
            </button>
          ))}
        </div>

        <span className="flex-1" />

        <div className="flex items-center gap-1">
          <button
            onClick={() => setZoom((z) => Math.max(MIN_ZOOM, z - 0.2))}
            style={{ color: "var(--app-tx-2)" }}
            aria-label="Zoom out"
          >
            <Minus size={14} weight="bold" />
          </button>
          <button
            onClick={() => setZoom(1)}
            className="tnum min-w-[42px] text-[11.5px]"
            style={{ color: "var(--app-tx-2)" }}
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            onClick={() => setZoom((z) => Math.min(MAX_ZOOM, z + 0.2))}
            style={{ color: "var(--app-tx-2)" }}
            aria-label="Zoom in"
          >
            <Plus size={14} weight="bold" />
          </button>
          <button
            onClick={fitZoomToHighlight}
            aria-label="Zoom to the highlight"
            style={{ color: "var(--app-tx-2)" }}
          >
            <ArrowsOut size={14} weight="bold" />
          </button>
        </div>
      </div>

      {evidence && !evidence.bbox && (
        <div
          className="px-4 py-2 text-[11.5px]"
          style={{ background: "var(--app-warn-soft)", color: "var(--app-warn)" }}
        >
          This line has no recorded position on the sheet — showing page{" "}
          {evidence.sourcePage ?? "?"} without a highlight.
        </div>
      )}

      <div ref={frameRef} className="min-h-0 flex-1 overflow-auto p-3">
        {failure ? (
          <div
            className="rounded-lg px-4 py-3 text-[12.5px]"
            style={{
              background: "var(--app-neg-soft)",
              border: "1px solid var(--app-neg-line)",
              color: "var(--app-neg)",
            }}
          >
            {failure}
            <button
              onClick={() =>
                setFailures((current) => {
                  const next = { ...current };
                  delete next[activeDoc.id];
                  return next;
                })
              }
              className="ml-2 underline underline-offset-2"
            >
              Try again
            </button>
          </div>
        ) : (
          <Document
            file={fileUrl}
            key={activeDoc.id}
            onLoadSuccess={({ numPages }) => setPageCount(numPages)}
            onLoadError={(err) =>
              setFailures((current) => ({
                ...current,
                [activeDoc.id]: `Could not open ${activeDoc.filename}: ${err.message}`,
              }))
            }
            loading={
              <div className="p-8 text-center text-[12.5px]" style={{ color: "var(--app-tx-3)" }}>
                Opening the drawing…
              </div>
            }
          >
            <div ref={pageRef} className="relative inline-block">
              <Page
                pageNumber={pageNumber}
                width={BASE_PAGE_WIDTH * zoom}
                onRenderSuccess={measurePage}
                renderAnnotationLayer={false}
                renderTextLayer={false}
              />
              {highlight && (
                <div
                  ref={highlightRef}
                  className="pointer-events-none absolute rounded-[3px]"
                  style={{
                    left: highlight.left,
                    top: highlight.top,
                    width: highlight.width,
                    height: highlight.height,
                    background: "rgba(129,140,248,0.22)",
                    border: "2px solid var(--app-accent)",
                    boxShadow: "0 0 0 9999px rgba(0,0,0,0.35)",
                  }}
                />
              )}
            </div>
          </Document>
        )}
      </div>

      {pageCount > 1 && (
        <div
          className="flex items-center gap-2 border-t px-4 py-2"
          style={{ borderColor: "var(--app-line)" }}
        >
          <button
            onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
            disabled={pageNumber <= 1}
            className="rounded px-2 py-1 text-[11.5px] disabled:opacity-40"
            style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
          >
            Previous
          </button>
          <span className="tnum flex-1 text-center text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
            {pageNumber} / {pageCount}
          </span>
          <button
            onClick={() => setPageNumber((p) => Math.min(pageCount, p + 1))}
            disabled={pageNumber >= pageCount}
            className="rounded px-2 py-1 text-[11.5px] disabled:opacity-40"
            style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
          >
            Next
          </button>
        </div>
      )}
    </aside>
  );
}
