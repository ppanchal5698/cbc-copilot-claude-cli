/**
 * The default loading state for the signed-in shell.
 *
 * Every route in this group is `force-dynamic` and blocks on the FastAPI
 * service, so before this file existed a navigation showed the previous screen
 * frozen until the API answered - indistinguishable from a click that missed.
 *
 * A parent loading.tsx covers its nested segments too, so this one file serves
 * the dashboard, the board, the catalog, the price books and settings; the bid
 * stages have their own because they carry a stage bar.
 */
export default function AppLoading() {
  return (
    <>
      <div
        className="flex h-[54px] shrink-0 items-center gap-4 border-b px-5"
        style={{ borderColor: "var(--app-line)", background: "var(--app-bg)" }}
      >
        <span className="skeleton h-3 w-40" />
        <span className="flex-1" />
        <span className="skeleton h-[34px] w-[200px]" />
        <span className="skeleton h-8 w-8 rounded-full" />
      </div>

      <main className="min-h-0 flex-1 overflow-hidden p-6" aria-busy="true" aria-live="polite">
        <span className="sr-only">Loading…</span>
        <div className="mb-6 flex items-end justify-between gap-4">
          <div className="flex flex-col gap-2">
            <span className="skeleton h-5 w-56" />
            <span className="skeleton h-3 w-80" />
          </div>
          <span className="skeleton h-9 w-28" />
        </div>

        <div
          className="overflow-hidden rounded-xl"
          style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
        >
          <div className="border-b px-4 py-3.5" style={{ borderColor: "var(--app-line)" }}>
            <span className="skeleton h-4 w-40" />
          </div>
          {Array.from({ length: 7 }).map((_, row) => (
            <div
              key={row}
              className="flex items-center gap-3 border-b px-4 py-3 last:border-b-0"
              style={{ borderColor: "var(--app-line)" }}
            >
              <span className="skeleton h-8 w-8 shrink-0 rounded-lg" />
              <span className="flex flex-1 flex-col gap-1.5">
                <span className="skeleton h-3 w-1/3" />
                <span className="skeleton h-2.5 w-1/4" />
              </span>
              <span className="skeleton h-5 w-24 shrink-0 rounded-full" />
            </div>
          ))}
        </div>
      </main>
    </>
  );
}
