"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/**
 * Shell-wide UI state.
 *
 * The notes drawer and the command palette open from several places - the
 * header, the action bar, a keyboard shortcut - so a small context beats
 * threading callbacks through four component layers.
 */
interface UiState {
  notesOpen: boolean;
  openNotes: (ref?: string) => void;
  closeNotes: () => void;
  notesRef: string | null;

  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;

  focusMode: boolean;
  toggleFocus: () => void;

  /** Bumped whenever a note is logged, so counts refresh without a page reload. */
  notesVersion: number;
  bumpNotes: () => void;
}

const Context = createContext<UiState | null>(null);

export function UiStateProvider({ children }: { children: React.ReactNode }) {
  const [notesOpen, setNotesOpen] = useState(false);
  const [notesRef, setNotesRef] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [notesVersion, setNotesVersion] = useState(0);

  useEffect(() => {
    try {
      setFocusMode(localStorage.getItem("opshub-focus") === "1");
    } catch {
      /* private browsing */
    }
  }, []);

  const openNotes = useCallback((ref?: string) => {
    setNotesRef(ref ?? null);
    setNotesOpen(true);
  }, []);

  const toggleFocus = useCallback(() => {
    setFocusMode((current) => {
      const next = !current;
      try {
        localStorage.setItem("opshub-focus", next ? "1" : "0");
      } catch {
        /* private browsing */
      }
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
      focusMode,
      toggleFocus,
      notesVersion,
      bumpNotes: () => setNotesVersion((v) => v + 1),
    }),
    [notesOpen, notesRef, openNotes, paletteOpen, focusMode, toggleFocus, notesVersion],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useUiState(): UiState {
  const value = useContext(Context);
  if (!value) throw new Error("useUiState must be used inside UiStateProvider");
  return value;
}
