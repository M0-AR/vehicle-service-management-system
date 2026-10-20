"use client";

// Single entry point for the REST API. Adds tenant routing (X-Tenant-Slug)
// and bearer auth, transparently refreshes the session once on 401, and
// normalises error payloads into ApiError.

import type { TokenPair } from "./types";

const BASE = "/api/v1";
const TOKEN_KEY = "vsms.token";
const WORKSPACE_KEY = "vsms.workspace";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export function getStoredWorkspace(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(WORKSPACE_KEY);
}

export function setStoredWorkspace(slug: string | null): void {
  if (typeof window === "undefined") return;
  if (slug) window.localStorage.setItem(WORKSPACE_KEY, slug);
  else window.localStorage.removeItem(WORKSPACE_KEY);
}

/** Tenant slug from the subdomain (demo.localhost) or the stored login. */
export function workspaceSlug(): string | null {
  if (typeof window === "undefined") return null;
  const host = window.location.hostname;
  const base = process.env.NEXT_PUBLIC_BASE_DOMAIN || "localhost";
  if (host !== base && host.endsWith("." + base)) {
    const first = host.slice(0, -(base.length + 1)).split(".")[0];
    if (first && first !== "www" && first !== "app") return first;
  }
  return getStoredWorkspace();
}

function tenantHeaders(): Record<string, string> {
  const slug = workspaceSlug();
  return slug ? { "X-Tenant-Slug": slug } : {};
}

let refreshPromise: Promise<boolean> | null = null;

export function refreshSession(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const res = await fetch(`${BASE}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: tenantHeaders(),
        });
        if (!res.ok) return false;
        const pair = (await res.json()) as TokenPair;
        setToken(pair.access_token);
        return true;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

export interface ApiOptions {
  method?: string;
  body?: unknown;
  /** internal: set to false on auth endpoints to avoid refresh recursion */
  retry?: boolean;
  headers?: Record<string, string>;
}

export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const headers: Record<string, string> = { ...tenantHeaders(), ...opts.headers };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${BASE}${path}`, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers,
    credentials: "include",
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  if (res.status === 401 && opts.retry !== false) {
    if (await refreshSession()) {
      return api<T>(path, { ...opts, retry: false });
    }
  }

  if (!res.ok) {
    let detail = res.statusText || "Request failed";
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Multipart upload (photos) with the same auth/tenant headers as `api`. */
export async function apiUpload<T>(path: string, file: File, field = "file"): Promise<T> {
  const headers: Record<string, string> = { ...tenantHeaders() };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const body = new FormData();
  body.append(field, file);

  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers,
    credentials: "include",
    body,
  });
  if (res.status === 401 && (await refreshSession())) {
    return apiUpload<T>(path, file, field);
  }
  if (!res.ok) {
    let detail = res.statusText || "Upload failed";
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** Fetch-with-auth + browser download for any API file response. */
export async function downloadApiFile(path: string, filename: string): Promise<void> {
  const headers = tenantHeaders();
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res = await fetch(`${BASE}${path}`, {
    headers,
    credentials: "include",
  });
  if (res.status === 401 && (await refreshSession())) {
    const fresh = getToken();
    if (fresh) headers["Authorization"] = `Bearer ${fresh}`;
    res = await fetch(`${BASE}${path}`, {
      headers,
      credentials: "include",
    });
  }
  if (!res.ok) throw new ApiError(res.status, "Download failed");

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Fetch-with-auth + browser download for the CSV exports. */
export async function downloadCsv(resource: string): Promise<void> {
  return downloadApiFile(`/settings/export/${resource}`, `${resource}.csv`);
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong";
}
