"use client";

// Public online booking — a customer picks an open slot and describes the
// job. No auth: the tenant comes from the URL slug.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { CalendarCheck, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, Input, Textarea } from "@/components/ui/fields";
import { ErrorState, LoadingBlock } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";
import { readableOn } from "@/lib/branding";
import { useApi } from "@/lib/hooks";
import type { BookingResult, PublicBooking } from "@/lib/types";

function BookingShell({
  workspace,
  children,
}: {
  workspace: { display_name: string; primary_color: string; accent_color: string };
  children: React.ReactNode;
}) {
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--brand-primary", workspace.primary_color);
    root.style.setProperty("--brand-accent", workspace.accent_color);
    root.style.setProperty("--brand-primary-fg", readableOn(workspace.primary_color));
  }, [workspace.primary_color, workspace.accent_color]);

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <header className="border-b border-[var(--border)]">
        <div className="mx-auto flex max-w-2xl items-center gap-2 px-4 py-4">
          <span className="rounded-lg bg-[var(--brand-primary)] p-1.5 text-[var(--brand-primary-fg)]">
            <Wrench className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="font-semibold tracking-tight">{workspace.display_name}</span>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-2xl px-4 py-8">
        {children}
      </main>
      <footer className="mx-auto max-w-2xl px-4 pb-8 text-xs text-[var(--muted-foreground)]">
        <p>
          Powered by{" "}
          <Link href="/" className="underline underline-offset-2">
            Vehicle Service Manager
          </Link>
        </p>
      </footer>
    </div>
  );
}

const FALLBACK = {
  display_name: "Vehicle Service Manager",
  primary_color: "#0f766e",
  accent_color: "#f59e0b",
};

export function BookingView() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug ?? "";
  const { data, error, isLoading, mutate } = useApi<PublicBooking>(
    slug ? `/public/booking/${slug}` : null,
  );

  const [slot, setSlot] = useState("");
  const [form, setForm] = useState({
    name: "",
    phone: "",
    email: "",
    plate_number: "",
    make: "",
    model: "",
    year: "",
    service_description: "",
    company: "",
  });
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<BookingResult | null>(null);

  // Group by the server-rendered label ("Mon 19 Oct, 09:00") so the times
  // always match the workshop's timezone, not the visitor's.
  const days = useMemo(() => {
    if (!data) return [];
    const groups = new Map<string, { label: string; slots: typeof data.slots }>();
    for (const s of data.slots) {
      const [day, time] = s.label.split(", ");
      const existing = groups.get(day);
      if (existing) existing.slots.push({ ...s, label: time ?? s.label });
      else groups.set(day, { label: day, slots: [{ ...s, label: time ?? s.label }] });
    }
    return [...groups.values()];
  }, [data]);

  const openDays = days.filter((d) => d.slots.some((s) => s.available));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!slot) {
      setSubmitError("Pick a time that works for you.");
      return;
    }
    setBusy(true);
    setSubmitError(null);
    try {
      const booking = await api<BookingResult>(`/public/booking/${slug}`, {
        body: {
          name: form.name.trim(),
          phone: form.phone.trim(),
          email: form.email.trim() || null,
          plate_number: form.plate_number.trim(),
          make: form.make.trim() || null,
          model: form.model.trim() || null,
          year: form.year ? Number.parseInt(form.year, 10) : null,
          service_description: form.service_description.trim(),
          preferred_at: slot,
          company: form.company,
        },
      });
      setResult(booking);
    } catch (err) {
      setSubmitError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <BookingShell workspace={FALLBACK}>
        <ErrorState
          message="Online booking is not available for this workshop right now. Please call them to book."
          retry={() => mutate()}
        />
      </BookingShell>
    );
  }
  if (isLoading && !data) return <LoadingBlock label="Loading available times" />;
  if (!data) return null;

  if (result) {
    return (
      <BookingShell workspace={data.workspace}>
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <span className="rounded-full bg-[color-mix(in_oklab,var(--success)_15%,transparent)] p-3">
              <CalendarCheck className="h-6 w-6 text-[var(--success)]" aria-hidden="true" />
            </span>
            <h1 className="text-xl font-semibold">Booking received</h1>
            <p className="max-w-md text-sm text-[var(--muted-foreground)]">
              {result.message}
            </p>
            <p className="text-sm">
              Reference <span className="font-medium">{result.number}</span>
            </p>
          </CardContent>
        </Card>
      </BookingShell>
    );
  }

  return (
    <BookingShell workspace={data.workspace}>
      <h1 className="text-2xl font-semibold tracking-tight">Book a service</h1>
      <p className="mt-1 text-sm text-[var(--muted-foreground)]">
        Choose an open time and tell us what your vehicle needs. Times are shown in{" "}
        {data.timezone}.
      </p>

      <form onSubmit={submit} className="mt-6 space-y-6">
        <Card>
          <CardContent className="space-y-4 pt-6">
            <h2 className="text-sm font-medium">1. Pick a time</h2>
            {openDays.length === 0 ? (
              <p className="text-sm text-[var(--muted-foreground)]">
                No open times in the next two weeks. Please call the workshop.
              </p>
            ) : (
              <div className="space-y-4">
                {openDays.map((day) => (
                  <div key={day.label}>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
                      {day.label}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {day.slots.map((s) => {
                        const active = slot === s.start;
                        return (
                          <button
                            key={s.start}
                            type="button"
                            disabled={!s.available}
                            aria-pressed={active}
                            onClick={() => setSlot(s.start)}
                            className={
                              active
                                ? "rounded-lg bg-[var(--brand-primary)] px-3 py-2 text-sm font-medium text-[var(--brand-primary-fg)]"
                                : s.available
                                  ? "rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm hover:bg-[var(--muted)]"
                                  : "cursor-not-allowed rounded-lg border border-[var(--border)] px-3 py-2 text-sm text-[var(--muted-foreground)] line-through opacity-60"
                            }
                          >
                            {s.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-4 pt-6">
            <h2 className="text-sm font-medium">2. Your details</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Name" htmlFor="b-name" required>
                <Input
                  id="b-name"
                  autoComplete="name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                />
              </Field>
              <Field label="Phone" htmlFor="b-phone" required>
                <Input
                  id="b-phone"
                  type="tel"
                  autoComplete="tel"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  required
                />
              </Field>
              <Field label="Email" htmlFor="b-email" hint="Optional — for written updates.">
                <Input
                  id="b-email"
                  type="email"
                  autoComplete="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </Field>
              <Field label="Licence plate" htmlFor="b-plate" required>
                <Input
                  id="b-plate"
                  value={form.plate_number}
                  onChange={(e) => setForm({ ...form, plate_number: e.target.value })}
                  required
                />
              </Field>
              <Field label="Make" htmlFor="b-make">
                <Input
                  id="b-make"
                  value={form.make}
                  onChange={(e) => setForm({ ...form, make: e.target.value })}
                  placeholder="Toyota"
                />
              </Field>
              <Field label="Model" htmlFor="b-model">
                <Input
                  id="b-model"
                  value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                  placeholder="Corolla"
                />
              </Field>
              <Field label="Year" htmlFor="b-year">
                <Input
                  id="b-year"
                  type="number"
                  min={1900}
                  max={2100}
                  value={form.year}
                  onChange={(e) => setForm({ ...form, year: e.target.value })}
                />
              </Field>
            </div>
            {/* Honeypot — hidden from people, tempting to bots. */}
            <div hidden aria-hidden="true">
              <label htmlFor="b-company">Company</label>
              <input
                id="b-company"
                tabIndex={-1}
                autoComplete="off"
                value={form.company}
                onChange={(e) => setForm({ ...form, company: e.target.value })}
              />
            </div>
            <Field label="What does your vehicle need?" htmlFor="b-description" required>
              <Textarea
                id="b-description"
                value={form.service_description}
                onChange={(e) => setForm({ ...form, service_description: e.target.value })}
                placeholder="Brakes squealing when stopping, plus an oil change."
                required
              />
            </Field>
            {submitError && (
              <p role="alert" className="text-sm text-[var(--destructive)]">
                {submitError}
              </p>
            )}
            <Button type="submit" loading={busy} disabled={openDays.length === 0}>
              Request booking
            </Button>
          </CardContent>
        </Card>
      </form>
    </BookingShell>
  );
}
