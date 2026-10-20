"use client";

// Tenant branding: fetched from /public/branding, applied as CSS variables
// (--brand-primary/--brand-accent) so the whole UI re-themes per workspace.

import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { api, workspaceSlug } from "./api";
import type { Branding } from "./types";

const FALLBACK: Branding = {
  slug: "",
  display_name: "",
  primary_color: "#0f766e",
  accent_color: "#f59e0b",
  logo_url: null,
  support_email: null,
  currency: "USD",
  locale: "en",
};

/** WCAG-aware readable foreground (#0b1220 / #ffffff) for a hex background. */
export function readableOn(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return "#ffffff";
  const value = parseInt(m[1], 16);
  const [r, g, b] = [(value >> 16) & 255, (value >> 8) & 255, value & 255].map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const contrastWhite = 1.05 / (luminance + 0.05);
  const contrastInk = (luminance + 0.05) / 0.0688; // vs #0b1220
  return contrastWhite >= contrastInk ? "#ffffff" : "#0b1220";
}

function applyVars(b: Branding) {
  const root = document.documentElement;
  root.style.setProperty("--brand-primary", b.primary_color || "#0f766e");
  root.style.setProperty("--brand-accent", b.accent_color || "#f59e0b");
  root.style.setProperty("--brand-primary-fg", readableOn(b.primary_color || "#0f766e"));
}

interface BrandingContextValue {
  branding: Branding;
  currency: string;
  ready: boolean;
}

const BrandingContext = createContext<BrandingContextValue>({
  branding: FALLBACK,
  currency: "USD",
  ready: false,
});

export function BrandingProvider({ children }: { children: React.ReactNode }) {
  const [branding, setBranding] = useState<Branding>(FALLBACK);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (workspaceSlug()) {
          const b = await api<Branding>("/public/branding");
          if (!cancelled) {
            setBranding(b);
            applyVars(b);
          }
        }
      } catch {
        /* platform host or unknown tenant — keep defaults */
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(
    () => ({ branding, currency: branding.currency || "USD", ready }),
    [branding, ready],
  );
  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>;
}

export function useBranding(): BrandingContextValue {
  return useContext(BrandingContext);
}
