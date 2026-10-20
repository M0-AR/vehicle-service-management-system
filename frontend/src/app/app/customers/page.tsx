"use client";

import { useMemo, useState } from "react";
import { MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { PageHeader, Pager, SearchInput } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown";
import { Field, Input, Textarea } from "@/components/ui/fields";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBranding } from "@/lib/branding";
import { money } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import type { Customer, CustomerSummary, Page } from "@/lib/types";

const PAGE_SIZE = 25;

interface FormState {
  name: string;
  email: string;
  phone: string;
  address: string;
  notes: string;
}

const EMPTY_FORM: FormState = { name: "", email: "", phone: "", address: "", notes: "" };

export default function CustomersPage() {
  const { user } = useAuth();
  const { currency } = useBranding();
  const canManage = ["owner", "admin", "manager"].includes(user?.role ?? "");
  const canDelete = ["owner", "admin"].includes(user?.role ?? "");

  const [q, setQ] = useState("");
  const debouncedQ = useDebounced(q);
  const [page, setPage] = useState(1);

  const query = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (debouncedQ) params.set("q", debouncedQ);
    return params.toString();
  }, [page, debouncedQ]);

  const { data, error, isLoading, mutate } = useApi<Page<CustomerSummary>>(`/customers?${query}`);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<CustomerSummary | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setFormOpen(true);
  }

  async function openEdit(id: string) {
    try {
      const customer = await api<Customer>(`/customers/${id}`);
      setEditing(customer);
      setForm({
        name: customer.name,
        email: customer.email ?? "",
        phone: customer.phone ?? "",
        address: customer.address ?? "",
        notes: customer.notes ?? "",
      });
      setFormError(null);
      setFormOpen(true);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    const body = {
      name: form.name.trim(),
      email: form.email.trim() || null,
      phone: form.phone.trim() || null,
      address: form.address.trim() || null,
      notes: form.notes.trim() || null,
    };
    try {
      if (editing) {
        await api(`/customers/${editing.id}`, { method: "PATCH", body });
        toast.success("Customer updated");
      } else {
        await api("/customers", { body });
        toast.success("Customer added");
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
      await api(`/customers/${deleting.id}`, { method: "DELETE" });
      toast.success(`Deleted ${deleting.name}`);
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
      <PageHeader title="Customers" description="People and businesses you service.">
        {canManage && (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add customer
          </Button>
        )}
      </PageHeader>

      <SearchInput
        value={q}
        onChange={(v) => {
          setQ(v);
          setPage(1);
        }}
        placeholder="Search name, email, phone…"
        label="Search customers"
        className="sm:max-w-xs"
      />

      {error && <ErrorState message="Could not load customers" retry={() => mutate()} />}
      {isLoading && !data && <TableSkeleton />}

      {data && data.items.length === 0 && (
        <EmptyState
          title="No customers found"
          description={q ? "Try a different search." : "Add your first customer to get started."}
          action={canManage && !q ? <Button onClick={openCreate}>Add customer</Button> : undefined}
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <Table caption="Customers">
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Phone</TH>
                <TH className="text-right">Vehicles</TH>
                <TH className="text-right">Open orders</TH>
                <TH className="text-right">Total billed</TH>
                <TH><span className="sr-only">Actions</span></TH>
              </TR>
            </THead>
            <TBody>
              {data.items.map((c) => (
                <TR key={c.id}>
                  <TD className="font-medium">{c.name}</TD>
                  <TD className="text-[var(--muted-foreground)]">{c.phone ?? "—"}</TD>
                  <TD className="text-right">{c.vehicle_count}</TD>
                  <TD className="text-right">{c.open_orders}</TD>
                  <TD className="text-right">{money(c.total_billed, currency)}</TD>
                  <TD className="w-12 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" aria-label={`Actions for ${c.name}`}>
                          <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        {canManage && (
                          <DropdownMenuItem onSelect={() => openEdit(c.id)}>
                            <Pencil className="h-4 w-4" aria-hidden="true" />
                            Edit
                          </DropdownMenuItem>
                        )}
                        {canDelete && (
                          <DropdownMenuItem danger onSelect={() => setDeleting(c)}>
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
          title={editing ? `Edit ${editing.name}` : "Add customer"}
          description={editing ? "Update the customer record." : "Create a new customer record."}
        >
          <form onSubmit={save} className="space-y-4">
            {formError && (
              <div role="alert" className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]">
                {formError}
              </div>
            )}
            <Field label="Name" htmlFor="c-name" required>
              <Input
                id="c-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Email" htmlFor="c-email">
                <Input
                  id="c-email"
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </Field>
              <Field label="Phone" htmlFor="c-phone">
                <Input
                  id="c-phone"
                  type="tel"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                />
              </Field>
            </div>
            <Field label="Address" htmlFor="c-address">
              <Input
                id="c-address"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
              />
            </Field>
            <Field label="Notes" htmlFor="c-notes">
              <Textarea
                id="c-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setFormOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                {editing ? "Save changes" : "Add customer"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent
          title={`Delete ${deleting?.name ?? "customer"}?`}
          description="This cannot be undone. Customers with vehicles or orders may be blocked from deletion."
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
