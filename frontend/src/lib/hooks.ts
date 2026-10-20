"use client";

import { useEffect, useState } from "react";
import useSWR, { type SWRConfiguration } from "swr";

import { api } from "./api";

/** SWR wrapper: GET `path` via the shared API client. */
export function useApi<T>(path: string | null, config?: SWRConfiguration<T>) {
  const { data, error, isLoading, isValidating, mutate } = useSWR<T>(
    path,
    (p: string) => api<T>(p),
    { keepPreviousData: true, revalidateOnFocus: false, ...config },
  );
  return { data, error, isLoading, isValidating, mutate };
}

export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

/** Auto-dismissing inline message state (success/error banners). */
export function useFlash(timeoutMs = 4000) {
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(() => setMessage(null), timeoutMs);
    return () => clearTimeout(t);
  }, [message, timeoutMs]);
  return { message, flashOk: (text: string) => setMessage({ kind: "ok", text }), flashErr: (text: string) => setMessage({ kind: "err", text }), clear: () => setMessage(null) };
}
