import { redirect } from "next/navigation";

import { auth } from "@/auth";
import { Rail } from "@/components/shell/rail";
import { ShellOverlays } from "@/components/shell/shell-overlays";
import { UiStateProvider } from "@/components/shell/ui-state";
import { api } from "@/lib/api";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session?.user) redirect("/signin");

  const user = {
    name: session.user.name ?? "Estimator",
    email: session.user.email ?? "",
    initials:
      (session.user as { initials?: string }).initials ??
      (session.user.name ?? "E")
        .split(" ")
        .map((part) => part[0])
        .slice(0, 2)
        .join("")
        .toUpperCase(),
  };

  // A stale price book is a live risk to every quote, so the count rides the nav.
  let staleBooks = 0;
  try {
    const books = await api.get<{ counts: { stale: number } }>("/api/price-books");
    staleBooks = books.counts.stale;
  } catch {
    /* the API being down is surfaced on the page itself, not here */
  }

  return (
    <UiStateProvider>
      <div className="flex h-screen overflow-hidden">
        <Rail staleBooks={staleBooks} user={user} />
        <div className="flex min-w-0 flex-1 flex-col">{children}</div>
      </div>
      <ShellOverlays />
    </UiStateProvider>
  );
}
