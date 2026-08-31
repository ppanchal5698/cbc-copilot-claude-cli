"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { signOut } from "next-auth/react";
import { MagnifyingGlass, Sun, Moon, Bell, PhoneCall } from "@phosphor-icons/react/dist/ssr";

import { useUiState } from "@/components/shell/ui-state";
import { proxyFetcher } from "@/lib/proxy-fetcher";
import type { CallsResponse } from "@/lib/types";

export interface Crumb {
  label: string;
  href?: string;
}

export function Header({
  crumbs,
  user,
  runPill,
  reviewCount,
  code,
}: {
  crumbs: Crumb[];
  user: { name: string; initials: string };
  runPill?: { label: string; tone: "running" | "done" | "failed" } | null;
  reviewCount?: number;
  code?: string | null;
}) {
  const { openNotes, setPaletteOpen, setTerminalOpen, focusMode, notesVersion, theme, toggleTheme } =
    useUiState();
  const [noteCount, setNoteCount] = useState<number | null>(null);

  useEffect(() => {
    if (!code) return;
    const controller = new AbortController();
    proxyFetcher<CallsResponse>(`/api/proxy/projects/${code}/calls`, controller.signal)
      .then((data) => setNoteCount(data.count))
      .catch(() => setNoteCount(null));
    return () => controller.abort();
  }, [code, notesVersion]);

  const toneColour =
    runPill?.tone === "failed"
      ? "var(--app-neg)"
      : runPill?.tone === "running"
        ? "var(--app-warn)"
        : "var(--app-pos)";

  return (
    <header
      className="flex h-[54px] shrink-0 items-center gap-4 border-b px-5"
      style={{ borderColor: "var(--app-line)", background: "var(--app-bg)" }}
    >
      <div className="flex items-center gap-1.5 text-[13px]">
        {crumbs.map((crumb, index) => (
          <span key={`${crumb.label}-${index}`} className="flex items-center gap-1.5">
            {index > 0 && <span style={{ color: "var(--app-tx-3)" }}>/</span>}
            {crumb.href ? (
              <Link href={crumb.href} style={{ color: "var(--app-tx-2)" }} className="no-underline">
                {crumb.label}
              </Link>
            ) : (
              <span style={{ color: "var(--app-tx)" }}>{crumb.label}</span>
            )}
          </span>
        ))}
      </div>

      <div className="flex-1" />

      <button
        onClick={() => setPaletteOpen(true)}
        aria-keyshortcuts="Control+K"
        className="hidden h-[34px] w-[200px] items-center gap-2 rounded-lg px-3 md:flex xl:w-[330px]"
        style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
      >
        <MagnifyingGlass size={15} weight="duotone" style={{ color: "var(--app-tx-3)" }} />
        <span className="flex-1 truncate text-left text-[13px]" style={{ color: "var(--app-tx-3)" }}>
          Ask or run a command…
        </span>
        <span
          className="hidden rounded px-1.5 py-0.5 text-[10.5px] xl:inline"
          style={{ background: "var(--app-panel-2)", color: "var(--app-tx-3)" }}
        >
          Ctrl + K
        </span>
      </button>

      {runPill && !focusMode && (
        // The pill is what you look at to ask "what is it doing?", so it is what
        // opens the real session rather than a separate control somewhere else.
        <button
          onClick={() => setTerminalOpen(true)}
          aria-label="Watch the Claude Code session"
          className="anim-fadein flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] transition"
          style={{ background: "var(--app-panel)", border: "1px solid var(--app-line)" }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: toneColour }}
          />
          <span style={{ color: "var(--app-tx-2)" }}>{runPill.label}</span>
          <span className="text-[10.5px]" style={{ color: "var(--app-tx-3)" }}>
            terminal
          </span>
        </button>
      )}

      <button
        onClick={() => openNotes()}
        className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[12px]"
        style={{ border: "1px solid var(--app-line)", color: "var(--app-tx-2)" }}
      >
        <PhoneCall size={14} weight="duotone" />
        Calls &amp; notes
        {noteCount !== null && noteCount > 0 && (
          <span
            className="tnum rounded-full px-1.5 text-[10.5px] font-semibold"
            style={{ background: "var(--app-accent-soft)", color: "var(--app-accent)" }}
          >
            {noteCount}
          </span>
        )}
      </button>

      <button
        onClick={toggleTheme}
        aria-label="Toggle theme"
        className="grid h-8 w-8 place-items-center rounded-md"
        style={{ color: "var(--app-tx-2)" }}
      >
        {theme === "dark" ? <Sun size={16} weight="duotone" /> : <Moon size={16} weight="duotone" />}
      </button>

      {/* The badge counts flagged lines, so the bell goes to them. It used to be
          a button with no handler: the one control on the page that did nothing. */}
      <Link
        href={code ? `/bids/${code}/extraction` : "/bids?stage=extraction"}
        aria-label={
          reviewCount
            ? `${reviewCount} line${reviewCount === 1 ? "" : "s"} need a look`
            : "Nothing flagged for review"
        }
        title={reviewCount ? "Go to the flagged lines" : "Nothing flagged"}
        className="relative grid h-8 w-8 place-items-center rounded-md no-underline"
        style={{ color: "var(--app-tx-2)" }}
      >
        <Bell size={16} weight="duotone" />
        {!!reviewCount && !focusMode && (
          <span
            className="tnum absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] font-semibold"
            style={{ background: "var(--app-neg)", color: "#fff" }}
          >
            {reviewCount}
          </span>
        )}
      </Link>

      <div className="flex items-center gap-2.5">
        <span
          className="grid h-8 w-8 place-items-center rounded-full text-[11.5px] font-semibold"
          style={{ background: "var(--app-accent-soft)", color: "var(--app-accent)" }}
        >
          {user.initials}
        </span>
        <span className="flex flex-col leading-tight">
          <span className="text-[12.5px] font-semibold">{user.name}</span>
          <span className="text-[11px]" style={{ color: "var(--app-pos)" }}>
            Online
          </span>
        </span>
        <button
          onClick={() => signOut({ callbackUrl: "/signin" })}
          className="text-[12px]"
          style={{ color: "var(--app-tx-3)" }}
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
