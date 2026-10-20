"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { toast } from "sonner";

import { FilterChips, PageHeader, Pager, SearchInput } from "@/components/page";
import { EstimateStatusBadge } from "@/components/estimate-status";
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
import type { Estimate, EstimateListItem, Page, VehicleSummary } from "@/lib/types";

const PAGE_SIZE = 25;

const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "draft", label: "Draft" },
  { value: "sent", label: "Sent" },
  { value: "approved", label: "Approved" },
  { value: "declined", label: "Declined" },
];

export default function EstimatesPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { currency } = useBranding();
  const role = user?.role ?? "";
  const canCreate = ["owner", "admin", "manager", "mechanic"].includes(role);

  const [q, setQ] = useState("");
  const debouncedQ = useDebounced(q);
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);

  const query = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (debouncedQ) params.set("q", debouncedQ);
    if (status !== "all") params.set("status", status);
    return params.toString();
  }, [page, debouncedQ, status]);

  const { data, error, isLoading, mutate } = useApi<Page<EstimateListItem>>(`/estimates?${query}`);
  const vehicles = useApi<Page<VehicleSummary>>("/vehicles?page_size=100");

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ vehicle_id: "", description: "", notes: "" });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function openCreate() {
    setForm({ vehicle_id: "", description: "", notes: "" });
    setFormError(null);
    setOpen(true);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const estimate = await api<Estimate>("/estimates", {
        body: {
          vehicle_id: form.vehicle_id,
          description: form.description.trim(),
          notes: form.notes.trim() || null,
          items: [],
        },
      });
      toast.success(`Estimate ${estimate.number} created`);
      setOpen(false);
      router.push(`/app/estimates/${estimate.id}`);
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Estimates"
        description="Quote work, send a link, and let the customer approve online."
      >
        {canCreate && (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            New estimate
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
          label="Search estimates"
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
      </div>

      {error && <ErrorState message="Could not load estimates" retry={() => mutate()} />}
      {isLoading && !data && <TableSkeleton />}

      {data && data.items.length === 0 && (
        <EmptyState
          title="No estimates yet"
          description={
            q || status !== "all"
              ? "Try a different search or filter."
              : "Create an estimate, add labour and parts, then send the approval link."
          }
          action={
            canCreate && !q && status === "all" ? (
              <Button onClick={openCreate}>New estimate</Button>
            ) : undefined
          }
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <Table caption="Estimates">
            <THead>
              <TR>
                <TH>Estimate</TH>
                <TH>Vehicle</TH>
                <TH>Customer</TH>
                <TH>Status</TH>
                <TH numeric>Total</TH>
                <TH className="hidden sm:table-cell">Created</TH>
              </TR>
            </THead>
            <TBody>
              {data.items.map((estimate) => (
                <TR key={estimate.id}>
                  <TD>
                    <Link
                      href={`/app/estimates/${estimate.id}`}
                      className="font-medium hover:underline"
                    >
                      {estimate.number}
                    </Link>
                    <p className="max-w-56 truncate text-xs text-[var(--muted-foreground)]">
                      {estimate.description}
                    </p>
                  </TD>
                  <TD>{estimate.vehicle_plate ?? "—"}</TD>
                  <TD className="text-[var(--muted-foreground)]">
                    {estimate.customer_name ?? "—"}
                  </TD>
                  <TD>
                    <EstimateStatusBadge status={estimate.status} />
                  </TD>
                  <TD numeric>{money(estimate.total, currency)}</TD>
                  <TD className="hidden text-[var(--muted-foreground)] sm:table-cell">
                    {formatDate(estimate.created_at)}
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
          title="New estimate"
          description="Pick the vehicle and describe the work — you can add line items next."
          wide
        >
          <form onSubmit={save} className="space-y-4">
            {formError && (
              <div
                role="alert"
                className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]"
              >
                {formError}
              </div>
            )}
            <Field label="Vehicle" htmlFor="est-vehicle" required>
              <Select
                id="est-vehicle"
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
            <Field label="Work to quote" htmlFor="est-description" required>
              <Textarea
                id="est-description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Full brake service: front pads, rotors and fluid."
                required
              />
            </Field>
            <Field label="Notes for the customer" htmlFor="est-notes">
              <Textarea
                id="est-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                Create estimate
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
