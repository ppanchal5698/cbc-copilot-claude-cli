"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/**
 * Shell-wide UI state.
 *
 * The notes drawer and the command palette open from several places - the
 * header, the action bar, a keyboard shortcut - so a small context beats
 * threading callbacks through four component layers.
 */
export type Theme = "dark" | "light";

interface UiState {
  notesOpen: boolean;
  openNotes: (ref?: string) => void;
  closeNotes: () => void;
  notesRef: string | null;

  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;

  /** The live Claude Code session for the bid on screen. */
  terminalOpen: boolean;
  setTerminalOpen: (open: boolean) => void;

  focusMode: boolean;
  toggleFocus: () => void;

  /** The palette, the header and the pre-paint script all used to own this. */
  theme: Theme;
  toggleTheme: () => void;

  /** Bumped whenever a note is logged, so counts refresh without a page reload. */
  notesVersion: number;
  bumpNotes: () => void;
}

const Context = createContext<UiState | null>(null);

/**
 * Read a persisted preference without breaking hydration.
 *
 * The server has no localStorage, so the first client render must match the
 * server's markup and the stored value can only be applied afterwards. Both
 * preferences are cosmetic, so a one-frame default is acceptable; the theme
 * itself is already applied pre-paint by the inline script in app/layout.tsx,
 * which is what actually stops the flash.
 */
function stored(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null; /* private browsing */
  }
}

function remember(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private browsing */
  }
}

export function UiStateProvider({ children }: { children: React.ReactNode }) {
  const [notesOpen, setNotesOpen] = useState(false);
  const [notesRef, setNotesRef] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [theme, setTheme] = useState<Theme>("dark");
  const [hydrated, setHydrated] = useState(false);
  const [notesVersion, setNotesVersion] = useState(0);

  // One pass after mount to pick up what the browser remembered. Guarded by a
  // flag rather than an empty dependency array so it cannot loop.
  if (!hydrated && typeof window !== "undefined") {
    setHydrated(true);
    setFocusMode(stored("opshub-focus") === "1");
    setTheme(stored("opshub-theme") === "light" ? "light" : "dark");
  }

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      remember("opshub-theme", next);
      return next;
    });
  }, []);

  const openNotes = useCallback((ref?: string) => {
    setNotesRef(ref ?? null);
    setNotesOpen(true);
  }, []);

  const toggleFocus = useCallback(() => {
    setFocusMode((current) => {
      const next = !current;
      remember("opshub-focus", next ? "1" : "0");
      return next;
    });
  }, []);

  // Ctrl/Cmd+K anywhere; C opens the call drawer unless you are typing.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
        return;
      }

      const target = event.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);

      if (!typing && event.key.toLowerCase() === "c" && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        setNotesOpen(true);
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo<UiState>(
    () => ({
      notesOpen,
      openNotes,
      closeNotes: () => setNotesOpen(false),
      notesRef,
      paletteOpen,
      setPaletteOpen,
      terminalOpen,
      setTerminalOpen,
      focusMode,
      toggleFocus,
      theme,
      toggleTheme,
      notesVersion,
      bumpNotes: () => setNotesVersion((v) => v + 1),
    }),
    [
      notesOpen,
      notesRef,
      openNotes,
      paletteOpen,
      terminalOpen,
      focusMode,
      toggleFocus,
      theme,
      toggleTheme,
      notesVersion,
    ],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useUiState(): UiState {
  const value = useContext(Context);
  if (!value) throw new Error("useUiState must be used inside UiStateProvider");
  return value;
}
