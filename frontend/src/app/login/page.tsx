"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/fields";
import { Spinner } from "@/components/ui/feedback";
import { errorMessage, workspaceSlug } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const DEMO_EMAIL = "owner@demo.example";
const DEMO_PASSWORD = "demo-password-123";

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center">
          <Spinner />
        </main>
      }
    >
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { user, ready, login } = useAuth();

  const demo = params.get("demo") === "1";
  const [slug, setSlug] = useState("");
  const [email, setEmail] = useState(demo ? DEMO_EMAIL : "");
  const [password, setPassword] = useState(demo ? DEMO_PASSWORD : "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSlug(workspaceSlug() ?? (demo ? "demo" : ""));
  }, [demo]);

  useEffect(() => {
    if (ready && user) router.replace("/app");
  }, [ready, user, router]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(slug.trim().toLowerCase(), email.trim(), password);
      router.replace("/app");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main id="main" className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="rounded-lg bg-[var(--brand-primary)] p-1.5 text-[var(--brand-primary-fg)]">
            <Wrench className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="text-lg font-semibold tracking-tight">Vehicle Service Manager</span>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Sign in</CardTitle>
            <CardDescription>Welcome back — enter your workspace details.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              {error && (
                <div
                  role="alert"
                  className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]"
                >
                  {error}
                </div>
              )}
              <Field
                label="Workspace"
                htmlFor="login-slug"
                hint="The identifier in your workspace URL."
              >
                <Input
                  id="login-slug"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  autoComplete="organization"
                  required
                />
              </Field>
              <Field label="Email" htmlFor="login-email">
                <Input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </Field>
              <Field label="Password" htmlFor="login-password">
                <Input
                  id="login-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </Field>
              <Button type="submit" className="w-full" loading={busy}>
                Sign in
              </Button>
            </form>

            {demo && (
              <p className="mt-4 rounded-lg bg-[var(--muted)] px-3 py-2 text-xs text-[var(--muted-foreground)]">
                Demo workspace pre-filled: <strong>demo</strong> / {DEMO_EMAIL} / {DEMO_PASSWORD}
              </p>
            )}
          </CardContent>
        </Card>

        <p className="mt-4 text-center text-sm text-[var(--muted-foreground)]">
          No workspace yet?{" "}
          <Link href="/signup" className="font-medium text-[var(--brand-text)] hover:underline">
            Create one free
          </Link>
        </p>
      </div>
    </main>
  );
}
