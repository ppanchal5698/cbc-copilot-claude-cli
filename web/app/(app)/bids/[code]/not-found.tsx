import Link from "next/link";
import { MagnifyingGlass } from "@phosphor-icons/react/dist/ssr";

/**
 * All four bid stages call notFound() on a 404 from the API. Until this file
 * existed that produced the stock Next 404, which says nothing about bids.
 */
export default function BidNotFound() {
  return (
    <main className="grid flex-1 place-items-center p-6">
      <div className="grid max-w-[460px] justify-items-center gap-3 text-center">
        <span
          className="grid h-11 w-11 place-items-center rounded-xl"
          style={{ background: "var(--app-panel-2)", color: "var(--app-tx-3)" }}
        >
          <MagnifyingGlass size={22} weight="duotone" />
        </span>

        <h1 className="text-[17px] font-semibold">No such bid</h1>

        <p className="text-[12.5px] leading-relaxed" style={{ color: "var(--app-tx-2)" }}>
          That bid number is not on this installation. It may have been removed, or the link may
          have been typed by hand.
        </p>

        <div className="mt-1 flex flex-wrap justify-center gap-2">
          <Link
            href="/bids"
            className="rounded-md px-3.5 py-2 text-[12.5px] font-semibold no-underline"
            style={{ background: "var(--app-accent)", color: "#fff" }}
          >
            Open the bid board
          </Link>
          <Link
            href="/dashboard"
            className="rounded-md px-3.5 py-2 text-[12.5px] no-underline"
            style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
          >
            Back to the dashboard
          </Link>
        </div>
      </div>
    </main>
  );
}
