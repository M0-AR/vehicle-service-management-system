"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { toast } from "sonner";

import { FilterChips, PageHeader, Pager, SearchInput } from "@/components/page";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/fields";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBranding } from "@/lib/branding";
import { formatDate, money } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import type { Location, OrderListItem, Page, User, VehicleSummary } from "@/lib/types";

const PAGE_SIZE = 25;

const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "scheduled", label: "Scheduled" },
  { value: "in_progress", label: "In progress" },
  { value: "awaiting_parts", label: "Awaiting parts" },
  { value: "completed", label: "Completed" },
  { value: "invoiced", label: "Invoiced" },
  { value: "cancelled", label: "Cancelled" },
];

interface FormState {
  vehicle_id: string;
  location_id: string;
  description: string;
  priority: string;
  odometer: string;
  scheduled_at: string;
  mechanic_id: string;
  estimated_cost: string;
  notes: string;
}

const EMPTY_FORM: FormState = {
  vehicle_id: "",
  location_id: "",
  description: "",
  priority: "normal",
  odometer: "",
  scheduled_at: "",
  mechanic_id: "",
  estimated_cost: "",
  notes: "",
};

export default function OrdersPage() {
  const { user } = useAuth();
  const { currency } = useBranding();
  const role = user?.role ?? "";
  const canCreate = ["owner", "admin", "manager"].includes(role);
  const canSeeStaff = ["owner", "admin", "manager"].includes(role);

  const [q, setQ] = useState("");
  const debouncedQ = useDebounced(q);
  const [status, setStatus] = useState("all");
  const [locationFilter, setLocationFilter] = useState("all");
  const [page, setPage] = useState(1);

  const query = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (debouncedQ) params.set("q", debouncedQ);
    if (status !== "all") params.set("status", status);
    if (locationFilter !== "all") params.set("location_id", locationFilter);
    return params.toString();
  }, [page, debouncedQ, status, locationFilter]);

  const { data, error, isLoading, mutate } = useApi<Page<OrderListItem>>(`/service-orders?${query}`);
  const vehicles = useApi<Page<VehicleSummary>>("/vehicles?page_size=100");
  const staff = useApi<Page<User>>(canSeeStaff ? "/staff?page_size=100" : null);
  const locations = useApi<Location[]>("/locations");
  const hasLocations = (locations.data?.length ?? 0) > 0;

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function openCreate() {
    const fallback = locations.data?.find((l) => l.is_default) ?? locations.data?.[0];
    setForm({ ...EMPTY_FORM, location_id: fallback?.id ?? "" });
    setFormError(null);
    setOpen(true);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await api("/service-orders", {
        body: {
          vehicle_id: form.vehicle_id,
          location_id: form.location_id || null,
          description: form.description.trim(),
          priority: form.priority,
          odometer: form.odometer ? Number.parseInt(form.odometer, 10) : null,
          scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : null,
          mechanic_id: form.mechanic_id || null,
          estimated_cost: form.estimated_cost ? Number.parseFloat(form.estimated_cost) : null,
          notes: form.notes.trim() || null,
        },
      });
      toast.success("Service order created");
      setOpen(false);
      mutate();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Service orders" description="Track every job from booking to invoice.">
        {canCreate && (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            New order
          </Button>
        )}
      </PageHeader>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchInput
          value={q}
          onChange={(v) => {
            setQ(v);
            setPage(1);
          }}
          placeholder="Search number, vehicle, description…"
          label="Search service orders"
          className="sm:max-w-xs"
        />
        <FilterChips
          options={STATUS_OPTIONS}
          value={status}
          onChange={(v) => {
            setStatus(v);
            setPage(1);
          }}
          label="Filter by status"
        />
        {hasLocations && (
          <Select
            aria-label="Filter by location"
            value={locationFilter}
            onChange={(e) => {
              setLocationFilter(e.target.value);
              setPage(1);
            }}
            className="sm:max-w-44"
          >
            <option value="all">All locations</option>
            {(locations.data ?? []).map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </Select>
        )}
      </div>

      {error && <ErrorState message="Could not load service orders" retry={() => mutate()} />}
      {isLoading && !data && <TableSkeleton />}

      {data && data.items.length === 0 && (
        <EmptyState
          title="No service orders found"
          description={
            q || status !== "all" || locationFilter !== "all"
              ? "Try a different search or filter."
              : "Create your first service order."
          }
          action={
            canCreate && !q && status === "all" && locationFilter === "all" ? (
              <Button onClick={openCreate}>New order</Button>
            ) : undefined
          }
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <Table caption="Service orders">
            <THead>
              <TR>
                <TH>Order</TH>
                <TH>Vehicle</TH>
                <TH>Customer</TH>
                {hasLocations && <TH className="hidden md:table-cell">Location</TH>}
                <TH>Status</TH>
                <TH>Priority</TH>
                <TH numeric>Total</TH>
                <TH className="hidden sm:table-cell">Created</TH>
              </TR>
            </THead>
            <TBody>
              {data.items.map((o) => (
                <TR key={o.id}>
                  <TD>
                    <Link href={`/app/orders/${o.id}`} className="font-medium hover:underline">
                      {o.number}
                    </Link>
                    <p className="max-w-56 truncate text-xs text-[var(--muted-foreground)]">
                      {o.description}
                    </p>
                  </TD>
                  <TD>{o.vehicle_plate ?? "—"}</TD>
                  <TD className="text-[var(--muted-foreground)]">{o.customer_name ?? "—"}</TD>
                  {hasLocations && (
                    <TD className="hidden text-[var(--muted-foreground)] md:table-cell">
                      {o.location_name ?? "—"}
                    </TD>
                  )}
                  <TD>
                    <StatusBadge status={o.status} kind="order" />
                  </TD>
                  <TD>
                    <StatusBadge status={o.priority} kind="priority" />
                  </TD>
                  <TD numeric>{money(o.total, currency)}</TD>
                  <TD className="hidden text-[var(--muted-foreground)] sm:table-cell">
                    {formatDate(o.created_at)}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pager page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} />
        </>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title="New service order"
          description="Book a job for a vehicle in your fleet."
          wide
        >
          <form onSubmit={save} className="space-y-4">
            {formError && (
              <div role="alert" className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]">
                {formError}
              </div>
            )}
            <Field label="Vehicle" htmlFor="o-vehicle" required>
              <Select
                id="o-vehicle"
                value={form.vehicle_id}
                onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}
                required
              >
                <option value="">— select a vehicle —</option>
                {(vehicles.data?.items ?? []).map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.plate_number} — {v.make} {v.model}
                  </option>
                ))}
              </Select>
            </Field>
            {hasLocations && (
              <Field label="Location" htmlFor="o-location">
                <Select
                  id="o-location"
                  value={form.location_id}
                  onChange={(e) => setForm({ ...form, location_id: e.target.value })}
                >
                  {(locations.data ?? []).map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                      {l.is_default ? " (default)" : ""}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field label="Problem / work to do" htmlFor="o-description" required>
              <Textarea
                id="o-description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                required
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Priority" htmlFor="o-priority">
                <Select
                  id="o-priority"
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: e.target.value })}
                >
                  {["low", "normal", "high", "urgent"].map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Scheduled for" htmlFor="o-scheduled">
                <Input
                  id="o-scheduled"
                  type="datetime-local"
                  value={form.scheduled_at}
                  onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
                />
              </Field>
              <Field label="Odometer (km)" htmlFor="o-odometer">
                <Input
                  id="o-odometer"
                  type="number"
                  min={0}
                  value={form.odometer}
                  onChange={(e) => setForm({ ...form, odometer: e.target.value })}
                />
              </Field>
              <Field label="Estimated cost" htmlFor="o-estimate">
                <Input
                  id="o-estimate"
                  type="number"
                  min={0}
                  step="0.01"
                  value={form.estimated_cost}
                  onChange={(e) => setForm({ ...form, estimated_cost: e.target.value })}
                />
              </Field>
              {canSeeStaff && (
                <Field label="Assign to" htmlFor="o-mechanic">
                  <Select
                    id="o-mechanic"
                    value={form.mechanic_id}
                    onChange={(e) => setForm({ ...form, mechanic_id: e.target.value })}
                  >
                    <option value="">— unassigned —</option>
                    {(staff.data?.items ?? [])
                      .filter((s) => s.is_active)
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} ({s.role})
                        </option>
                      ))}
                  </Select>
                </Field>
              )}
            </div>
            <Field label="Notes" htmlFor="o-notes">
              <Textarea
                id="o-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                Create order
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
