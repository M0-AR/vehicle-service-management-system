"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Check, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/fields";
import { Spinner } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useDebounced } from "@/lib/hooks";
import { usePlans, planPrice } from "@/lib/plans";
import { cn } from "@/lib/cn";
import type { SignupResponse, SlugCheck } from "@/lib/types";

const SLUG_RE = /^[a-z0-9][a-z0-9-]{1,30}$/;

function slugify(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
}

export default function SignupPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center">
          <Spinner />
        </main>
      }
    >
      <SignupWizard />
    </Suspense>
  );
}

function SignupWizard() {
  const router = useRouter();
  const params = useSearchParams();
  const { adoptSession } = useAuth();

  const [step, setStep] = useState(1);
  const [businessName, setBusinessName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const requestedPlan = params.get("plan");
  const [plan, setPlan] = useState<string>(requestedPlan ?? "free");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const debouncedSlug = useDebounced(slug, 400);
  const { data: plans } = usePlans();
  const [slugCheck, setSlugCheck] = useState<SlugCheck | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    if (!slugTouched) setSlug(slugify(businessName));
  }, [businessName, slugTouched]);

  useEffect(() => {
    if (!SLUG_RE.test(debouncedSlug)) {
      setSlugCheck(null);
      return;
    }
    let cancelled = false;
    setChecking(true);
    api<SlugCheck>(`/public/signup/check?slug=${encodeURIComponent(debouncedSlug)}`, { retry: false })
      .then((r) => {
        if (!cancelled) setSlugCheck(r);
      })
      .catch(() => {
        if (!cancelled) setSlugCheck(null);
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedSlug]);

  const step1Valid =
    businessName.trim().length >= 2 &&
    SLUG_RE.test(slug) &&
    slugCheck?.available === true;
  const step2Valid =
    name.trim().length >= 2 &&
    /.+@.+\..+/.test(email) &&
    password.length >= 8 &&
    password === confirm;

  const status = useMemo(() => {
    if (checking) return { tone: "muted", text: "Checking availability…" };
    if (!slug) return { tone: "muted", text: "" };
    if (!SLUG_RE.test(slug))
      return { tone: "err", text: "3–32 characters: lowercase letters, numbers, dashes." };
    if (slugCheck && !slugCheck.available)
      return { tone: "err", text: slugCheck.message || "That workspace name is taken." };
    if (slugCheck?.available)
      return { tone: "ok", text: `${slug}.${process.env.NEXT_PUBLIC_BASE_DOMAIN || "localhost"} is available` };
    return { tone: "muted", text: "" };
  }, [checking, slug, slugCheck]);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const res = await api<SignupResponse>("/public/signup", {
        retry: false,
        body: {
          business_name: businessName.trim(),
          name: name.trim(),
          slug,
          email: email.trim(),
          password,
        },
      });
      await adoptSession(res.slug, {
        access_token: res.access_token,
        token_type: res.token_type,
        expires_in: res.expires_in,
      });
      router.replace(
        plan === "free" ? "/app" : `/app/settings?tab=billing&upgrade=${plan}`,
      );
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main id="main" className="flex min-h-screen flex-col items-center px-4 py-10">
      <div className="w-full max-w-lg">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="rounded-lg bg-[var(--brand-primary)] p-1.5 text-[var(--brand-primary-fg)]">
            <Wrench className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="text-lg font-semibold tracking-tight">Create your workspace</span>
        </div>

        <ol className="mb-6 flex items-center justify-center gap-2 text-sm" aria-label="Signup progress">
          {["Business", "Account", "Plan"].map((label, i) => {
            const n = i + 1;
            const done = step > n;
            const active = step === n;
            return (
              <li key={label} className="flex items-center gap-2">
                <span
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold",
                    done
                      ? "bg-[var(--success)] text-[var(--success-foreground)]"
                      : active
                        ? "bg-[var(--brand-primary)] text-[var(--brand-primary-fg)]"
                        : "bg-[var(--muted)] text-[var(--muted-foreground)]",
                  )}
                  aria-current={active ? "step" : undefined}
                >
                  {done ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : n}
                </span>
                <span className={cn(active ? "font-medium" : "text-[var(--muted-foreground)]")}>
                  {label}
                </span>
                {n < 3 && <span className="text-[var(--border)]">—</span>}
              </li>
            );
          })}
        </ol>

        <Card>
          {step === 1 && (
            <>
              <CardHeader>
                <CardTitle>Your business</CardTitle>
                <CardDescription>This creates your private workspace.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="Business name" htmlFor="su-business" required>
                  <Input
                    id="su-business"
                    value={businessName}
                    onChange={(e) => setBusinessName(e.target.value)}
                    placeholder="Northside Auto Repair"
                    autoComplete="organization"
                  />
                </Field>
                <Field
                  label="Workspace URL"
                  htmlFor="su-slug"
                  required
                  hint={status.tone === "muted" && status.text ? status.text : undefined}
                  error={status.tone === "err" ? status.text : null}
                >
                  <div className="flex items-center gap-2">
                    <Input
                      id="su-slug"
                      value={slug}
                      onChange={(e) => {
                        setSlugTouched(true);
                        setSlug(e.target.value.toLowerCase());
                      }}
                      aria-invalid={status.tone === "err"}
                      aria-describedby={status.text ? `su-slug-${status.tone}` : undefined}
                    />
                  </div>
                </Field>
                {status.tone === "ok" && (
                  <p id="su-slug-ok" className="text-xs font-medium text-[var(--success)]">
                    {status.text}
                  </p>
                )}
                <div className="flex justify-end">
                  <Button disabled={!step1Valid} onClick={() => setStep(2)}>
                    Continue
                  </Button>
                </div>
              </CardContent>
            </>
          )}

          {step === 2 && (
            <>
              <CardHeader>
                <CardTitle>Your account</CardTitle>
                <CardDescription>You will be the workspace owner.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="Full name" htmlFor="su-name" required>
                  <Input
                    id="su-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="name"
                  />
                </Field>
                <Field label="Work email" htmlFor="su-email" required>
                  <Input
                    id="su-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                  />
                </Field>
                <Field
                  label="Password"
                  htmlFor="su-password"
                  required
                  hint="At least 8 characters."
                  error={
                    password && password.length < 8 ? "Password must be at least 8 characters." : null
                  }
                >
                  <Input
                    id="su-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                    aria-invalid={Boolean(password && password.length < 8)}
                  />
                </Field>
                <Field
                  label="Confirm password"
                  htmlFor="su-confirm"
                  required
                  error={confirm && confirm !== password ? "Passwords do not match." : null}
                >
                  <Input
                    id="su-confirm"
                    type="password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    autoComplete="new-password"
                    aria-invalid={Boolean(confirm && confirm !== password)}
                  />
                </Field>
                <div className="flex justify-between">
                  <Button variant="secondary" onClick={() => setStep(1)}>
                    Back
                  </Button>
                  <Button disabled={!step2Valid} onClick={() => setStep(3)}>
                    Continue
                  </Button>
                </div>
              </CardContent>
            </>
          )}

          {step === 3 && (
            <>
              <CardHeader>
                <CardTitle>Pick a plan</CardTitle>
                <CardDescription>Start free — upgrade whenever you need more.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {error && (
                  <div
                    role="alert"
                    className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]"
                  >
                    {error}
                  </div>
                )}
                <div role="radiogroup" aria-label="Plan" className="grid gap-3">
                  {(plans ?? []).map((option) => {
                    const selected = plan === option.id;
                    const blurb =
                      option.id === "free"
                        ? `${option.limits.users ?? "—"} staff · ${option.limits.vehicles ?? "—"} vehicles`
                        : option.id === "pro"
                          ? "Custom domain, white-label, API and audit log."
                          : "Unlimited scale, BYOK and priority support.";
                    return (
                      <button
                        key={option.id}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => setPlan(option.id)}
                        className={cn(
                          "rounded-xl border p-4 text-left transition-colors",
                          selected
                            ? "border-[var(--brand-primary)] bg-[var(--muted)]"
                            : "border-[var(--border)] hover:border-[var(--muted-foreground)]",
                        )}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{option.name}</span>
                          <span className="text-sm text-[var(--muted-foreground)]">
                            {planPrice(option)}/mo
                          </span>
                        </div>
                        <p className="mt-1 text-sm text-[var(--muted-foreground)]">{blurb}</p>
                      </button>
                    );
                  })}
                </div>
                {plan !== "free" && (
                  <p className="rounded-lg bg-[var(--muted)] px-3 py-2 text-xs text-[var(--muted-foreground)]">
                    Your workspace is created right away; you will confirm the{" "}
                    {plans?.find((p) => p.id === plan)?.name ?? plan} subscription in
                    Settings → Billing.
                  </p>
                )}
                <div className="flex justify-between">
                  <Button variant="secondary" onClick={() => setStep(2)} disabled={busy}>
                    Back
                  </Button>
                  <Button onClick={submit} loading={busy}>
                    Create workspace
                  </Button>
                </div>
              </CardContent>
            </>
          )}
        </Card>

        <p className="mt-4 text-center text-sm text-[var(--muted-foreground)]">
          Already have one?{" "}
          <Link href="/login" className="font-medium text-[var(--brand-text)] hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
