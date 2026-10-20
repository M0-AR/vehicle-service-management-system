"use client";

import { useMemo, useState } from "react";
import { MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { FilterChips, PageHeader, Pager, SearchInput } from "@/components/page";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown";
import { Field, Input, Select, Textarea } from "@/components/ui/fields";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi, useDebounced } from "@/lib/hooks";
import type { CustomerSummary, Page, Vehicle, VehicleSummary, VinDecode } from "@/lib/types";

const PAGE_SIZE = 25;

const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "in_service", label: "In service" },
  { value: "retired", label: "Retired" },
];

interface FormState {
  plate_number: string;
  make: string;
  model: string;
  year: string;
  vin: string;
  color: string;
  fuel_type: string;
  mileage: string;
  customer_id: string;
  notes: string;
}

const EMPTY_FORM: FormState = {
  plate_number: "",
  make: "",
  model: "",
  year: "",
  vin: "",
  color: "",
  fuel_type: "petrol",
  mileage: "",
  customer_id: "",
  notes: "",
};

export default function VehiclesPage() {
  const { user } = useAuth();
  const canManage = ["owner", "admin", "manager"].includes(user?.role ?? "");
  const canDelete = ["owner", "admin"].includes(user?.role ?? "");

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

  const { data, error, isLoading, mutate } = useApi<Page<VehicleSummary>>(`/vehicles?${query}`);
  const customers = useApi<Page<CustomerSummary>>("/customers?page_size=100");

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Vehicle | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<VehicleSummary | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setFormOpen(true);
  }

  async function openEdit(id: string) {
    try {
      const vehicle = await api<Vehicle>(`/vehicles/${id}`);
      setEditing(vehicle);
      setForm({
        plate_number: vehicle.plate_number,
        make: vehicle.make,
        model: vehicle.model,
        year: vehicle.year ? String(vehicle.year) : "",
        vin: vehicle.vin ?? "",
        color: vehicle.color ?? "",
        fuel_type: vehicle.fuel_type,
        mileage: String(vehicle.mileage ?? ""),
        customer_id: vehicle.customer_id ?? "",
        notes: vehicle.notes ?? "",
      });
      setFormError(null);
      setFormOpen(true);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const [vinBusy, setVinBusy] = useState(false);

  async function decodeVin() {
    const vin = form.vin.trim().toUpperCase();
    if (!vin) {
      toast.error("Enter a VIN first");
      return;
    }
    setVinBusy(true);
    try {
      const result = await api<VinDecode>(
        `/vehicles/decode-vin?vin=${encodeURIComponent(vin)}`,
      );
      if (!result.decoded) {
        toast.error(result.message || "That VIN could not be decoded");
        return;
      }
      setForm((prev) => ({
        ...prev,
        vin: result.vin || vin,
        make: result.make || prev.make,
        model: result.model || prev.model,
        year: result.year ? String(result.year) : prev.year,
        fuel_type: result.fuel_type || prev.fuel_type,
      }));
      toast.success("Vehicle details filled from VIN");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setVinBusy(false);
    }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    const body = {
      plate_number: form.plate_number.trim(),
      make: form.make.trim(),
      model: form.model.trim(),
      year: form.year ? Number.parseInt(form.year, 10) : null,
      vin: form.vin.trim() || null,
      color: form.color.trim() || null,
      fuel_type: form.fuel_type,
      mileage: form.mileage ? Number.parseInt(form.mileage, 10) : 0,
      customer_id: form.customer_id || null,
      notes: form.notes.trim() || null,
    };
    try {
      if (editing) {
        await api(`/vehicles/${editing.id}`, { method: "PATCH", body });
        toast.success("Vehicle updated");
      } else {
        await api("/vehicles", { body });
        toast.success("Vehicle added");
      }
      setFormOpen(false);
      mutate();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api(`/vehicles/${deleting.id}`, { method: "DELETE" });
      toast.success(`Deleted ${deleting.plate_number}`);
      setDeleting(null);
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Vehicles" description="Every vehicle your workshop services.">
        {canManage && (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add vehicle
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
          placeholder="Search plate, make, model…"
          label="Search vehicles"
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

      {error && <ErrorState message="Could not load vehicles" retry={() => mutate()} />}
      {isLoading && !data && <TableSkeleton />}

      {data && data.items.length === 0 && (
        <EmptyState
          title="No vehicles found"
          description={q || status !== "all" ? "Try a different search or filter." : "Add your first vehicle to get started."}
          action={canManage && !q && status === "all" ? <Button onClick={openCreate}>Add vehicle</Button> : undefined}
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <Table caption="Vehicles">
            <THead>
              <TR>
                <TH>Plate</TH>
                <TH>Vehicle</TH>
                <TH>Customer</TH>
                <TH>Status</TH>
                <TH className="text-right">Open orders</TH>
                <TH><span className="sr-only">Actions</span></TH>
              </TR>
            </THead>
            <TBody>
              {data.items.map((v) => (
                <TR key={v.id}>
                  <TD className="font-medium">{v.plate_number}</TD>
                  <TD>
                    {v.make} {v.model}
                    {v.year ? ` (${v.year})` : ""}
                  </TD>
                  <TD className="text-[var(--muted-foreground)]">{v.customer_name ?? "—"}</TD>
                  <TD>
                    <StatusBadge status={v.status} kind="vehicle" />
                  </TD>
                  <TD className="text-right">{v.open_orders}</TD>
                  <TD className="w-12 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" aria-label={`Actions for ${v.plate_number}`}>
                          <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        {canManage && (
                          <DropdownMenuItem onSelect={() => openEdit(v.id)}>
                            <Pencil className="h-4 w-4" aria-hidden="true" />
                            Edit
                          </DropdownMenuItem>
                        )}
                        {canDelete && (
                          <DropdownMenuItem danger onSelect={() => setDeleting(v)}>
                            <Trash2 className="h-4 w-4" aria-hidden="true" />
                            Delete
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pager page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} />
        </>
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent
          title={editing ? `Edit ${editing.plate_number}` : "Add vehicle"}
          description={editing ? "Update the vehicle record." : "Register a vehicle in your fleet."}
          wide
        >
          <form onSubmit={save} className="space-y-4">
            {formError && (
              <div role="alert" className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]">
                {formError}
              </div>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Plate number" htmlFor="v-plate" required>
                <Input
                  id="v-plate"
                  value={form.plate_number}
                  onChange={(e) => setForm({ ...form, plate_number: e.target.value })}
                  required
                />
              </Field>
              <Field label="Customer" htmlFor="v-customer">
                <Select
                  id="v-customer"
                  value={form.customer_id}
                  onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
                >
                  <option value="">— none —</option>
                  {(customers.data?.items ?? []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Make" htmlFor="v-make" required>
                <Input
                  id="v-make"
                  value={form.make}
                  onChange={(e) => setForm({ ...form, make: e.target.value })}
                  required
                />
              </Field>
              <Field label="Model" htmlFor="v-model" required>
                <Input
                  id="v-model"
                  value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                  required
                />
              </Field>
              <Field label="Year" htmlFor="v-year">
                <Input
                  id="v-year"
                  type="number"
                  min={1900}
                  max={2100}
                  value={form.year}
                  onChange={(e) => setForm({ ...form, year: e.target.value })}
                />
              </Field>
              <Field
                label="VIN"
                htmlFor="v-vin"
                hint="17 characters — use Decode to fill make, model and year."
              >
                <div className="flex gap-2">
                  <Input
                    id="v-vin"
                    value={form.vin}
                    onChange={(e) => setForm({ ...form, vin: e.target.value.toUpperCase() })}
                    maxLength={17}
                    autoCapitalize="characters"
                    spellCheck={false}
                    className="font-mono"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={decodeVin}
                    loading={vinBusy}
                    disabled={form.vin.trim().length !== 17}
                  >
                    Decode
                  </Button>
                </div>
              </Field>
              <Field label="Color" htmlFor="v-color">
                <Input
                  id="v-color"
                  value={form.color}
                  onChange={(e) => setForm({ ...form, color: e.target.value })}
                />
              </Field>
              <Field label="Fuel type" htmlFor="v-fuel">
                <Select
                  id="v-fuel"
                  value={form.fuel_type}
                  onChange={(e) => setForm({ ...form, fuel_type: e.target.value })}
                >
                  {["petrol", "diesel", "electric", "hybrid", "lpg", "other"].map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Mileage" htmlFor="v-mileage">
                <Input
                  id="v-mileage"
                  type="number"
                  min={0}
                  value={form.mileage}
                  onChange={(e) => setForm({ ...form, mileage: e.target.value })}
                />
              </Field>
            </div>
            <Field label="Notes" htmlFor="v-notes">
              <Textarea
                id="v-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setFormOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                {editing ? "Save changes" : "Add vehicle"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent
          title={`Delete ${deleting?.plate_number ?? "vehicle"}?`}
          description="This cannot be undone. Vehicles with service history may be blocked from deletion."
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete} loading={deleteBusy}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
