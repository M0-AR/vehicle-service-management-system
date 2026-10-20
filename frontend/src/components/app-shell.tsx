"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Boxes,
  Car,
  Check,
  ChevronDown,
  ClipboardList,
  FileText,
  Gauge,
  LogOut,
  Megaphone,
  Menu,
  Monitor,
  Moon,
  Receipt,
  ScrollText,
  Settings,
  Sun,
  Truck,
  Users,
  Wrench,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown";
import { LoadingBlock } from "@/components/ui/feedback";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";
import { useTheme, type ThemeChoice } from "@/lib/theme";

const THEMES: { value: ThemeChoice; label: string; icon: LucideIcon }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "system", label: "System", icon: Monitor },
  { value: "dark", label: "Dark", icon: Moon },
];

const NAV = [
  { href: "/app", label: "Dashboard", icon: Gauge },
  { href: "/app/vehicles", label: "Vehicles", icon: Car },
  { href: "/app/customers", label: "Customers", icon: Users },
  { href: "/app/orders", label: "Service orders", icon: ClipboardList },
  { href: "/app/estimates", label: "Estimates", icon: FileText },
  { href: "/app/invoices", label: "Invoices", icon: Receipt },
  { href: "/app/inventory", label: "Inventory", icon: Boxes, feature: "inventory" },
  { href: "/app/suppliers", label: "Suppliers", icon: Truck, feature: "suppliers" },
  { href: "/app/marketing", label: "Marketing", icon: Megaphone, feature: "marketing" },
  { href: "/app/audit", label: "Audit log", icon: ScrollText },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { ready, user, tenant, entitlements, logout } = useAuth();
  const { choice, setChoice } = useTheme();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);

  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  if (!ready) return <LoadingBlock label="Loading workspace" />;
  if (!user) return null;

  const nav = (
    <nav aria-label="Workspace" className="flex flex-1 flex-col gap-1">
      {NAV.filter(
        (item) => !("feature" in item) || entitlements?.features?.[item.feature as string],
      ).map((item) => {
        const active =
          item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-[var(--sidebar-active-bg)] font-medium text-[var(--foreground)] shadow-[inset_3px_0_0_0_var(--sidebar-accent)]"
                : "text-[var(--muted-foreground)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--foreground)]",
            )}
          >
            <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="flex min-h-screen bg-[var(--background)]">
      {/* Desktop sidebar */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--sidebar)] p-4 lg:flex">
        <WorkspaceHeader name={tenant?.name ?? "Workspace"} plan={entitlements?.name ?? tenant?.plan} />
        <div className="mt-6 flex flex-1 flex-col">{nav}</div>
        <p className="px-3 text-xs text-[var(--muted-foreground)]">{tenant?.slug}</p>
      </aside>

      {/* Mobile drawer */}
      {navOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-slate-950/40"
            onClick={() => setNavOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 flex w-64 flex-col bg-[var(--sidebar)] p-4 shadow-xl">
            <div className="flex items-center justify-between">
              <WorkspaceHeader name={tenant?.name ?? "Workspace"} plan={entitlements?.name ?? tenant?.plan} />
              <button
                type="button"
                onClick={() => setNavOpen(false)}
                className="rounded-md p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--muted)]"
              >
                <X className="h-5 w-5" aria-hidden="true" />
                <span className="sr-only">Close</span>
              </button>
            </div>
            <div className="mt-6 flex flex-1 flex-col">{nav}</div>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-[var(--border)] bg-[var(--card)] px-4">
          <div className="flex items-center gap-2 lg:hidden">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              className="rounded-md p-2 text-[var(--muted-foreground)] hover:bg-[var(--muted)]"
              aria-expanded={navOpen}
              aria-label="Open navigation"
            >
              <Menu className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
          <div className="hidden flex-1 lg:block" />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-[var(--muted)]"
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--brand-primary)] text-xs font-semibold text-[var(--brand-primary-fg)]">
                  {initials(user.name)}
                </span>
                <span className="hidden sm:inline">{user.name}</span>
                <ChevronDown className="h-4 w-4 text-[var(--muted-foreground)]" aria-hidden="true" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuLabel>{user.email}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>Theme</DropdownMenuLabel>
              {THEMES.map((item) => (
                <DropdownMenuItem key={item.value} onSelect={() => setChoice(item.value)}>
                  <item.icon className="h-4 w-4" aria-hidden="true" />
                  {item.label}
                  {choice === item.value && (
                    <Check className="ml-auto h-4 w-4" aria-hidden="true" />
                  )}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                danger
                onSelect={async () => {
                  await logout();
                  router.replace("/login");
                }}
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        <main id="main" className="flex-1 px-4 py-6 sm:px-6">
          <div className="mx-auto w-full max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );

  function WorkspaceHeader({ name, plan }: { name: string; plan?: string }) {
    return (
      <div className="flex items-center gap-2 px-1">
        <span className="rounded-lg bg-[var(--brand-primary)] p-1.5 text-[var(--brand-primary-fg)]">
          <Wrench className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{name}</p>
          {plan && (
            <p className="text-xs capitalize text-[var(--muted-foreground)]">{plan} plan</p>
          )}
        </div>
      </div>
    );
  }
}
