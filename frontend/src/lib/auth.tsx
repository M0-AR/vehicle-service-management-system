"use client";

// Auth state for the whole app: token bootstrap, login, logout, /me data
// (user + tenant + entitlements). Entitlements drive feature gating in the UI.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { api, getToken, setStoredWorkspace, setToken } from "./api";
import type { Me, Plan, TenantInfo, TokenPair, User } from "./types";

interface AuthContextValue {
  ready: boolean;
  user: User | null;
  tenant: TenantInfo | null;
  entitlements: Plan | null;
  login: (slug: string, email: string, password: string) => Promise<void>;
  adoptSession: (slug: string, pair: TokenPair) => Promise<void>;
  logout: () => Promise<void>;
  reloadMe: () => Promise<void>;
  hasFeature: (name: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [tenant, setTenant] = useState<TenantInfo | null>(null);
  const [entitlements, setEntitlements] = useState<Plan | null>(null);

  const reloadMe = useCallback(async () => {
    const me = await api<Me>("/auth/me");
    setUser(me.user);
    setTenant(me.tenant);
    setEntitlements(me.entitlements);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (getToken()) {
          await reloadMe();
        }
      } catch {
        if (!cancelled) {
          setToken(null);
          setUser(null);
          setTenant(null);
          setEntitlements(null);
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadMe]);

  const login = useCallback(
    async (slug: string, email: string, password: string) => {
      setStoredWorkspace(slug);
      const pair = await api<TokenPair>("/auth/login", {
        body: { email, password },
        retry: false,
      });
      setToken(pair.access_token);
      await reloadMe();
    },
    [reloadMe],
  );

  const adoptSession = useCallback(
    async (slug: string, pair: TokenPair) => {
      setStoredWorkspace(slug);
      setToken(pair.access_token);
      await reloadMe();
    },
    [reloadMe],
  );

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST", retry: false });
    } catch {
      /* session already gone */
    }
    setToken(null);
    setUser(null);
    setTenant(null);
    setEntitlements(null);
  }, []);

  const hasFeature = useCallback(
    (name: string) => entitlements?.features?.[name] === true,
    [entitlements],
  );

  const value = useMemo(
    () => ({ ready, user, tenant, entitlements, login, adoptSession, logout, reloadMe, hasFeature }),
    [ready, user, tenant, entitlements, login, adoptSession, logout, reloadMe, hasFeature],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
