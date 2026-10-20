import Link from "next/link";
import { Loader2, Lock, PackageOpen, TriangleAlert } from "lucide-react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/cn";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-5 w-5 animate-spin text-[var(--muted-foreground)]", className)} aria-hidden="true" />;
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-3 py-16 text-sm text-[var(--muted-foreground)]">
      <Spinner />
      <span>{label}…</span>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-[var(--muted)]", className)} aria-hidden="true" />;
}

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div role="status" aria-label="Loading table">
      <span className="sr-only">Loading…</span>
      <div className="space-y-3 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex gap-4">
            {Array.from({ length: cols }).map((__, c) => (
              <Skeleton key={c} className={cn("h-5", c === 0 ? "w-40" : "flex-1")} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
        <span className="rounded-full bg-[var(--muted)] p-3">
          <PackageOpen className="h-6 w-6 text-[var(--muted-foreground)]" aria-hidden="true" />
        </span>
        <div>
          <p className="font-medium">{title}</p>
          {description && (
            <p className="mt-1 text-sm text-[var(--muted-foreground)]">{description}</p>
          )}
        </div>
        {action}
      </CardContent>
    </Card>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <Card className="border-[color-mix(in_oklab,var(--destructive)_35%,transparent)]">
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <TriangleAlert className="h-6 w-6 text-[var(--destructive)]" aria-hidden="true" />
        <p className="text-sm font-medium text-[var(--destructive)]">{message}</p>
        {retry && (
          <Button variant="secondary" size="sm" onClick={retry}>
            Try again
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export function UpgradeNotice({ feature, detail }: { feature: string; detail?: string }) {
  return (
    <Card className="border-[color-mix(in_oklab,var(--warning)_35%,transparent)] bg-[color-mix(in_oklab,var(--warning)_8%,transparent)]">
      <CardContent className="flex flex-col items-start gap-3 py-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="rounded-full bg-[color-mix(in_oklab,var(--warning)_16%,transparent)] p-2">
            <Lock className="h-4 w-4 text-[color-mix(in_oklab,var(--warning)_65%,var(--foreground))]" aria-hidden="true" />
          </span>
          <div>
            <p className="font-medium text-[var(--foreground)]">{feature} is available on Pro</p>
            <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">
              {detail ?? "Upgrade your plan to unlock this feature."}
            </p>
          </div>
        </div>
        <Link href="/app/settings?tab=billing" className={buttonVariants({ size: "sm" })}>
          View plans
        </Link>
      </CardContent>
    </Card>
  );
}
