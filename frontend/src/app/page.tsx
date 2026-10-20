import Link from "next/link";
import {
  CalendarClock,
  Car,
  Palette,
  Receipt,
  ScrollText,
  ShieldCheck,
  Users,
  Wrench,
} from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PricingGrid } from "@/components/pricing";

const FEATURES = [
  {
    icon: Car,
    title: "Fleet & customers",
    text: "Track vehicles, service history and customer records in one place. Search by plate, VIN or owner.",
  },
  {
    icon: Wrench,
    title: "Service order workflow",
    text: "Scheduled → in progress → awaiting parts → completed. Mechanics see exactly what to do next.",
  },
  {
    icon: Receipt,
    title: "Quotes & invoicing",
    text: "Build estimates from labour and parts, convert completed jobs to invoices in one click, mark payments.",
  },
  {
    icon: CalendarClock,
    title: "Scheduling that fits",
    text: "Plan the week with an upcoming-jobs view and per-mechanic assignment.",
  },
  {
    icon: Users,
    title: "Roles & staff",
    text: "Owner, manager, mechanic, viewer — everyone gets the right level of access.",
  },
  {
    icon: Palette,
    title: "Your brand",
    text: "White-label colours, logo and your own domain on the Pro plan.",
  },
  {
    icon: ShieldCheck,
    title: "Secure by design",
    text: "Every workspace is isolated at the database level. Your data never leaks across tenants.",
  },
  {
    icon: ScrollText,
    title: "Audit & exports",
    text: "Full activity log and CSV exports for accounting, on every plan that needs them.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[var(--background)]">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <div className="flex items-center gap-2">
          <span className="rounded-lg bg-[var(--brand-primary)] p-1.5 text-[var(--brand-primary-fg)]">
            <Wrench className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="text-lg font-semibold tracking-tight">Vehicle Service Manager</span>
        </div>
        <nav aria-label="Main" className="flex items-center gap-2">
          <Link href="/login" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            Sign in
          </Link>
          <Link href="/signup" className={buttonVariants({ size: "sm" })}>
            Start free
          </Link>
        </nav>
      </header>

      <main id="main">
        <section className="mx-auto max-w-6xl px-4 pb-14 pt-10 sm:px-6 sm:pt-16">
          <div className="max-w-3xl">
            <Badge tone="brand">Built for independent workshops</Badge>
            <h1 className="mt-4 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
              Run your vehicle service business on autopilot
            </h1>
            <p className="mt-4 max-w-2xl text-lg text-[var(--muted-foreground)]">
              Fleet records, service orders, mechanic scheduling and invoicing — in one secure
              workspace per business. Start free in under a minute, no credit card required.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link href="/signup" className={buttonVariants({ size: "lg" })}>
                Create your workspace
              </Link>
              <Link href="/login?demo=1" className={buttonVariants({ variant: "secondary", size: "lg" })}>
                Try the live demo
              </Link>
            </div>
            <p className="mt-3 text-sm text-[var(--muted-foreground)]">
              Running locally? The seeded demo workspace is ready on the sign-in page.
            </p>
          </div>
        </section>

        <section aria-labelledby="features-heading" className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
          <h2 id="features-heading" className="text-2xl font-semibold tracking-tight">
            Everything a service shop needs
          </h2>
          <p className="mt-2 max-w-2xl text-[var(--muted-foreground)]">
            Designed with mechanics and service managers — fast on a phone in the workshop, deep
            enough for the back office.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((f) => (
              <Card key={f.title}>
                <CardContent className="pt-6">
                  <f.icon className="h-6 w-6 text-[var(--brand-text)]" aria-hidden="true" />
                  <h3 className="mt-3 font-medium">{f.title}</h3>
                  <p className="mt-1.5 text-sm text-[var(--muted-foreground)]">{f.text}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <section aria-labelledby="pricing-heading" className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
          <h2 id="pricing-heading" className="text-2xl font-semibold tracking-tight">
            Simple pricing
          </h2>
          <p className="mt-2 max-w-2xl text-[var(--muted-foreground)]">
            Start free, upgrade when the workshop grows. Every plan includes tenant isolation,
            encrypted data and unlimited customers.
          </p>
          <div className="mt-8">
            <PricingGrid />
          </div>
          <p className="mt-4 text-xs text-[var(--muted-foreground)]">
            Prices in USD, excluding applicable taxes. Cancel anytime.
          </p>
        </section>
      </main>

      <footer className="border-t border-[var(--border)]">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-sm text-[var(--muted-foreground)] sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>© {new Date().getFullYear()} Vehicle Service Manager</p>
          <nav aria-label="Footer" className="flex gap-4">
            <Link href="/login" className="hover:text-[var(--foreground)]">
              Sign in
            </Link>
            <Link href="/signup" className="hover:text-[var(--foreground)]">
              Create workspace
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
