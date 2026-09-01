"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FocusCard } from "@/components/shell/focus-card";
import {
  DiamondsFour,
  House,
  SquaresFour,
  Package,
  Books,
  SlidersHorizontal,
} from "@phosphor-icons/react/dist/ssr";

const NAV = [
  { href: "/dashboard", label: "Dashboard", Icon: House },
  { href: "/bids", label: "Bid board", Icon: SquaresFour },
  { href: "/catalog", label: "Product catalog", Icon: Package },
  { href: "/price-books", label: "Price books", Icon: Books },
  { href: "/settings", label: "Settings", Icon: SlidersHorizontal },
];

export function Rail({
  staleBooks,
  user,
}: {
  staleBooks?: number;
  user: { name: string; initials: string };
}) {
  const pathname = usePathname();

  return (
    <nav
      className="flex h-full w-[212px] shrink-0 flex-col border-r"
      style={{ background: "var(--app-bg-2)", borderColor: "var(--app-line)" }}
    >
      <div className="flex items-center gap-2.5 px-5 py-[18px]">
        <span
          className="grid h-7 w-7 place-items-center rounded-md"
          style={{ background: "var(--app-accent-soft)", color: "var(--app-accent)" }}
        >
          <DiamondsFour size={17} weight="duotone" />
        </span>
        <span className="text-[15px] font-bold tracking-[0.02em]">OPS·HUB</span>
      </div>

      <div className="flex flex-col gap-0.5 px-3">
        {NAV.map(({ href, label, Icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] no-underline transition"
              style={{
                background: active ? "var(--app-accent-soft)" : "transparent",
                color: active ? "var(--app-accent)" : "var(--app-tx-2)",
                border: `1px solid ${active ? "var(--app-accent-line)" : "transparent"}`,
              }}
            >
              <Icon size={16} weight="duotone" />
              <span className="flex-1">{label}</span>
              {href === "/price-books" && !!staleBooks && (
                <span
                  className="tnum rounded-full px-1.5 text-[10.5px] font-semibold"
                  style={{ background: "var(--app-neg-soft)", color: "var(--app-neg)" }}
                >
                  {staleBooks}
                </span>
              )}
            </Link>
          );
        })}
      </div>

      <div className="flex-1" />
      <FocusCard user={user} />
    </nav>
  );
}
