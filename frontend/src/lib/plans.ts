"use client";

// Plan catalog comes from the backend (/public/plans) so marketing copy and
// checkout never drift from the billing source of truth.

import useSWR from "swr";

import { api } from "./api";
import type { Plan } from "./types";

export function usePlans() {
  return useSWR<Plan[]>("/public/plans", (p: string) => api<Plan[]>(p), {
    revalidateOnFocus: false,
    dedupingInterval: 5 * 60_000,
  });
}

export function planPrice(plan: Plan): string {
  return plan.price_monthly_usd === 0 ? "$0" : `$${plan.price_monthly_usd}`;
}

export function planLimit(plan: Plan, key: string): string {
  const value = plan.limits?.[key];
  if (value === undefined) return "—";
  return value === -1 ? "Unlimited" : String(value);
}
