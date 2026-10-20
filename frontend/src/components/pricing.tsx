"use client";

import Link from "next/link";
import { Check } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { usePlans, planPrice } from "@/lib/plans";
import { cn } from "@/lib/cn";

const PLAN_COPY: Record<string, { blurb: string; bullets: string[]; cta: string; href: string }> = {
  free: {
    blurb: "For a single bay getting organised.",
    bullets: [
      "Up to 3 staff",
      "50 vehicles, 100 orders / month",
      "Fleet, orders and invoicing",
    ],
    cta: "Start free",
    href: "/signup",
  },
  pro: {
    blurb: "For busy workshops that need the whole toolbox.",
    bullets: [
      "20 staff, 1,000 vehicles",
      "Custom domain + white-label",
      "API keys, audit log, CSV exports",
    ],
    cta: "Start 14-day trial",
    href: "/signup?plan=pro",
  },
  enterprise: {
    blurb: "Multi-location groups and franchises.",
    bullets: [
      "Unlimited staff, vehicles and orders",
      "Bring your own keys (BYOK)",
      "Priority support and onboarding",
    ],
    cta: "Talk to us",
    href: "/signup?plan=enterprise",
  },
};

export function PricingGrid({ compact = false }: { compact?: boolean }) {
  const { data: plans, error } = usePlans();

  if (error) {
    return (
      <p className="text-sm text-[var(--muted-foreground)]">
        Pricing is temporarily unavailable. Please try again shortly.
      </p>
    );
  }

  if (!plans) {
    return (
      <div
        className={cn("grid gap-6", compact ? "sm:grid-cols-2" : "md:grid-cols-3")}
        aria-hidden="true"
      >
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-64 animate-pulse rounded-xl border border-[var(--border)] bg-[var(--muted)]"
          />
        ))}
      </div>
    );
  }

  return (
    <div className={cn("grid gap-6", compact ? "sm:grid-cols-2" : "md:grid-cols-3")}>
      {plans.map((plan) => {
        const copy = PLAN_COPY[plan.id] ?? {
          blurb: "",
          bullets: [],
          cta: "Get started",
          href: `/signup?plan=${plan.id}`,
        };
        const highlighted = plan.id === "pro";
        return (
          <Card
            key={plan.id}
            className={highlighted ? "border-[var(--brand-primary)] shadow-sm" : undefined}
          >
            <CardContent className="flex h-full flex-col pt-6">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-medium">{plan.name}</h3>
                {highlighted && <Badge tone="brand">Most popular</Badge>}
              </div>
              <p className="mt-3">
                <span className="text-3xl font-semibold">{planPrice(plan)}</span>
                <span className="text-[var(--muted-foreground)]"> / month</span>
              </p>
              <p className="mt-1 text-sm text-[var(--muted-foreground)]">{copy.blurb}</p>
              <ul className="mt-5 flex-1 space-y-2 text-sm">
                {copy.bullets.map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <Check
                      className="mt-0.5 h-4 w-4 shrink-0 text-[var(--success)]"
                      aria-hidden="true"
                    />
                    {item}
                  </li>
                ))}
              </ul>
              <Link
                href={copy.href}
                className={buttonVariants({
                  variant: highlighted ? "default" : "secondary",
                  className: "mt-6 w-full",
                })}
              >
                {copy.cta}
              </Link>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
