"use client";

// Theme system (docs/UI-REDESIGN.md §3.3): Light / System / Dark, persisted in
// localStorage. The blocking script in layout.tsx applies the class before
// first paint; this provider keeps React state in sync afterwards.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type ThemeChoice = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "vsms.theme";

function prefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

function resolve(choice: ThemeChoice): ResolvedTheme {
  if (choice === "system") return prefersDark() ? "dark" : "light";
  return choice;
}

function apply(resolved: ResolvedTheme) {
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

interface ThemeContextValue {
  choice: ThemeChoice;
  resolved: ResolvedTheme;
  setChoice: (choice: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  choice: "system",
  resolved: "light",
  setChoice: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>("system");

  useEffect(() => {
    let stored: ThemeChoice = "system";
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      if (value === "light" || value === "dark" || value === "system") stored = value;
    } catch {
      /* storage unavailable — stay on system */
    }
    setChoiceState(stored);
    apply(resolve(stored));
  }, []);

  useEffect(() => {
    if (choice !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply(resolve("system"));
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [choice]);

  const setChoice = useCallback((next: ThemeChoice) => {
    setChoiceState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
    apply(resolve(next));
  }, []);

  const value = useMemo(
    () => ({ choice, resolved: resolve(choice), setChoice }),
    [choice, setChoice],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
