"use client";

import Link from "next/link";
import {
  CalendarClock,
  Car,
  ClipboardList,
  Receipt,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-react";

import { PageHeader } from "@/components/page";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, TableSkeleton } from "@/components/ui/feedback";
import { StatusBadge } from "@/components/ui/badge";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useBranding } from "@/lib/branding";
import { formatDate, money, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { DashboardStats } from "@/lib/types";

export default function DashboardPage() {
  const { currency } = useBranding();
  const { data, error, isLoading, mutate } = useApi<DashboardStats>("/dashboard/stats");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Today at a glance across your workshop."
      />

      {error && <ErrorState message="Could not load dashboard" retry={() => mutate()} />}
      {isLoading && !data && <TableSkeleton rows={4} cols={4} />}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              icon={<Car className="h-4 w-4" aria-hidden="true" />}
              label="Vehicles"
              value={String(data.vehicles_total)}
              sub={`${data.vehicles_in_service} in service`}
              href="/app/vehicles"
            />
            <StatCard
              icon={<Users className="h-4 w-4" aria-hidden="true" />}
              label="Customers"
              value={String(data.customers_total)}
              href="/app/customers"
            />
            <StatCard
              icon={<ClipboardList className="h-4 w-4" aria-hidden="true" />}
              label="Open orders"
              value={String(data.orders_open)}
              href="/app/orders"
            />
            <StatCard
              icon={<TrendingUp className="h-4 w-4" aria-hidden="true" />}
              label="Revenue (30 days)"
              value={money(data.revenue_30d, currency)}
              sub={`${money(data.revenue_mtd, currency)} this month`}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Orders by status</CardTitle>
              </CardHeader>
              <CardContent>
                <BarList counts={data.orders_by_status} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Money owed</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-3xl font-semibold">{money(data.unpaid_total, currency)}</p>
                <p className="text-sm text-[var(--muted-foreground)]">
                  {data.unpaid_count === 0
                    ? "All invoices settled."
                    : `across ${data.unpaid_count} unpaid invoice${data.unpaid_count === 1 ? "" : "s"}`}
                </p>
                <Link
                  href="/app/invoices"
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--brand-text)] hover:underline"
                >
                  <Wallet className="h-4 w-4" aria-hidden="true" />
                  Review invoices
                </Link>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Upcoming</CardTitle>
              </CardHeader>
              <CardContent>
                {data.upcoming.length === 0 ? (
                  <p className="py-6 text-center text-sm text-[var(--muted-foreground)]">
                    Nothing scheduled ahead.
                  </p>
                ) : (
                  <ul className="divide-y divide-[var(--border)]">
                    {data.upcoming.map((order) => (
                      <li key={order.id} className="flex items-center justify-between gap-3 py-3">
                        <div className="min-w-0">
                          <Link
                            href={`/app/orders/${order.id}`}
                            className="font-medium hover:underline"
                          >
                            {order.number}
                          </Link>
                          <p className="truncate text-sm text-[var(--muted-foreground)]">
                            {order.vehicle_plate ?? "—"}
                            {order.customer_name ? ` · ${order.customer_name}` : ""}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2 text-sm text-[var(--muted-foreground)]">
                          <CalendarClock className="h-4 w-4" aria-hidden="true" />
                          {formatDate(order.scheduled_at)}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Recent orders</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table caption="Recent service orders" className="rounded-none border-0 bg-transparent">
                  <THead>
                    <TR>
                      <TH>Order</TH>
                      <TH>Vehicle</TH>
                      <TH>Status</TH>
                      <TH className="text-right">Total</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {data.recent_orders.map((order) => (
                      <TR key={order.id}>
                        <TD>
                          <Link href={`/app/orders/${order.id}`} className="font-medium hover:underline">
                            {order.number}
                          </Link>
                        </TD>
                        <TD className="text-[var(--muted-foreground)]">{order.vehicle_plate ?? "—"}</TD>
                        <TD>
                          <StatusBadge status={order.status} kind="order" />
                        </TD>
                        <TD className="text-right">{money(order.total ?? "0", currency)}</TD>
                      </TR>
                    ))}
                    {data.recent_orders.length === 0 && (
                      <TR>
                        <TD colSpan={4} className="py-6 text-center text-[var(--muted-foreground)]">
                          No orders yet.
                        </TD>
                      </TR>
                    )}
                  </TBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  sub,
  href,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  href?: string;
}) {
  const body = (
    <Card className="h-full transition-colors hover:border-[var(--brand-primary)]">
      <CardContent className="pt-5">
        <div className="flex items-center gap-2 text-[var(--muted-foreground)]">
          {icon}
          <span className="text-sm">{label}</span>
        </div>
        <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
        {sub && <p className="mt-1 text-xs text-[var(--muted-foreground)]">{sub}</p>}
      </CardContent>
    </Card>
  );
  return href ? (
    <Link href={href} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}

function BarList({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).filter(([, n]) => n > 0);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  if (entries.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-[var(--muted-foreground)]">
        No service orders yet — create your first one.
      </p>
    );
  }
  return (
    <ul className="space-y-3">
      {entries.map(([status, count]) => (
        <li key={status}>
          <div className="flex items-center justify-between text-sm">
            <span>{titleCase(status)}</span>
            <span className="font-medium">{count}</span>
          </div>
          <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[var(--muted)]">
            <div
              className="h-full rounded-full bg-[var(--brand-primary)]"
              style={{ width: `${Math.round((count / max) * 100)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
