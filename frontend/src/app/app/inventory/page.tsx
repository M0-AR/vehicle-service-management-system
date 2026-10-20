"use client";

import { useMemo, useState } from "react";
import {
  Archive,
  Boxes,
  PackagePlus,
  Pencil,
  Plus,
  TriangleAlert,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader, Pager, SearchInput } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/fields";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBranding } from "@/lib/branding";
import { money } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import type { InventorySummary, Page, Part } from "@/lib/types";

const PAGE_SIZE = 25;

function qty(value: string | number): string {
  const n = typeof value === "string" ? Number.parseFloat(value) : value;
  return Number.isFinite(n)
    ? n.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : "—";
}

const EMPTY_FORM = {
  name: "",
  sku: "",
  category: "",
  brand: "",
  supplier: "",
  location: "",
  cost: "",
  price: "",
  stock_qty: "",
  reorder_level: "",
  notes: "",
};

type PartForm = typeof EMPTY_FORM;

export default function InventoryPage() {
  const { user, hasFeature } = useAuth();
  const { currency } = useBranding();
  const role = user?.role ?? "";
  const canWrite = ["owner", "admin", "manager"].includes(role);
  const enabled = hasFeature("inventory");

  const [q, setQ] = useState("");
  const debouncedQ = useDebounced(q);
  const [lowOnly, setLowOnly] = useState(false);
  const [page, setPage] = useState(1);

  const query = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (debouncedQ) params.set("q", debouncedQ);
    if (lowOnly) params.set("low_stock", "true");
    return params.toString();
  }, [page, debouncedQ, lowOnly]);

  const parts = useApi<Page<Part>>(enabled ? `/inventory/parts?${query}` : null);
  const summary = useApi<InventorySummary>(enabled ? "/inventory/summary" : null);

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Part | null>(null);
  const [form, setForm] = useState<PartForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [adjusting, setAdjusting] = useState<Part | null>(null);
  const [adjust, setAdjust] = useState({ direction: "in", quantity: "", note: "" });
  const [adjustingBusy, setAdjustingBusy] = useState(false);

  const [archiving, setArchiving] = useState<Part | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);

  function set<K extends keyof PartForm>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setOpen(true);
  }

  function openEdit(part: Part) {
    setEditing(part);
    setForm({
      name: part.name,
      sku: part.sku,
      category: part.category ?? "",
      brand: part.brand ?? "",
      supplier: part.supplier ?? "",
      location: part.location ?? "",
      cost: part.cost,
      price: part.price,
      stock_qty: part.stock_qty,
      reorder_level: part.reorder_level,
      notes: part.notes ?? "",
    });
    setFormError(null);
    setOpen(true);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const payload = {
        name: form.name.trim(),
        sku: form.sku.trim() || null,
        category: form.category.trim() || null,
        brand: form.brand.trim() || null,
        supplier: form.supplier.trim() || null,
        location: form.location.trim() || null,
        cost: Number.parseFloat(form.cost) || 0,
        price: Number.parseFloat(form.price) || 0,
        reorder_level: Number.parseFloat(form.reorder_level) || 0,
        notes: form.notes.trim() || null,
      };
      if (editing) {
        await api<Part>(`/inventory/parts/${editing.id}`, {
          method: "PATCH",
          body: payload,
        });
        toast.success("Part updated");
      } else {
        await api<Part>("/inventory/parts", {
          body: { ...payload, stock_qty: Number.parseFloat(form.stock_qty) || 0 },
        });
        toast.success("Part added");
      }
      setOpen(false);
      parts.mutate();
      summary.mutate();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function saveAdjust(event: React.FormEvent) {
    event.preventDefault();
    if (!adjusting) return;
    const quantity = Number.parseFloat(adjust.quantity);
    if (!quantity || quantity <= 0) {
      toast.error("Enter a quantity greater than zero");
      return;
    }
    setAdjustingBusy(true);
    try {
      await api<Part>(`/inventory/parts/${adjusting.id}/adjust`, {
        body: {
          delta: adjust.direction === "in" ? quantity : -quantity,
          reason: adjust.direction === "in" ? "received" : "adjustment",
          note: adjust.note.trim() || null,
        },
      });
      toast.success(
        adjust.direction === "in" ? "Stock received" : "Stock adjusted",
      );
      setAdjusting(null);
      setAdjust({ direction: "in", quantity: "", note: "" });
      parts.mutate();
      summary.mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setAdjustingBusy(false);
    }
  }

  async function archive() {
    if (!archiving) return;
    setArchiveBusy(true);
    try {
      await api<{ ok: boolean }>(`/inventory/parts/${archiving.id}`, { method: "DELETE" });
      toast.success("Part archived");
      setArchiving(null);
      parts.mutate();
      summary.mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setArchiveBusy(false);
    }
  }

  if (!enabled) {
    return (
      <div className="space-y-6">
        <PageHeader title="Inventory" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Boxes className="h-8 w-8 text-[var(--muted-foreground)]" aria-hidden="true" />
            <p className="text-sm font-medium">Inventory is available on Pro and Enterprise.</p>
            <p className="max-w-sm text-sm text-[var(--muted-foreground)]">
              Track parts, quantities and reorder levels, and draw stock straight from
              service orders.
            </p>
            <Button onClick={() => (window.location.href = "/app/settings")}>
              View plans
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const total = parts.data?.total ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader title="Inventory" description="Parts, stock levels and reorder alerts.">
        {canWrite && (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" /> Add part
          </Button>
        )}
      </PageHeader>

      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-[var(--muted-foreground)]">
                Active parts
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {summary.data?.parts ?? "—"}
              </p>
            </div>
            <Boxes className="h-5 w-5 text-[var(--muted-foreground)]" aria-hidden="true" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-[var(--muted-foreground)]">
                Low stock
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {summary.data?.low_stock ?? "—"}
              </p>
            </div>
            <TriangleAlert
              className={`h-5 w-5 ${
                (summary.data?.low_stock ?? 0) > 0
                  ? "text-[var(--warning,var(--destructive))]"
                  : "text-[var(--muted-foreground)]"
              }`}
              aria-hidden="true"
            />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-[var(--muted-foreground)]">
                Stock value (cost)
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {money(summary.data?.stock_value, currency)}
              </p>
            </div>
            <PackagePlus className="h-5 w-5 text-[var(--muted-foreground)]" aria-hidden="true" />
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchInput
          value={q}
          onChange={(value) => {
            setQ(value);
            setPage(1);
          }}
          placeholder="Search name or SKU"
          label="Search parts"
          className="sm:max-w-xs"
        />
        <Button
          variant={lowOnly ? "default" : "secondary"}
          onClick={() => {
            setLowOnly((prev) => !prev);
            setPage(1);
          }}
        >
          <TriangleAlert className="h-4 w-4" aria-hidden="true" />
          Low stock only
        </Button>
      </div>

      {parts.error ? (
        <ErrorState message={errorMessage(parts.error)} retry={() => parts.mutate()} />
      ) : parts.isLoading ? (
        <TableSkeleton cols={6} />
      ) : total === 0 ? (
        <EmptyState
          title={lowOnly ? "No low-stock parts" : "No parts yet"}
          description={
            lowOnly
              ? "Everything is above its reorder level."
              : "Add your first part to start tracking stock."
          }
          action={
            canWrite && !lowOnly ? <Button onClick={openCreate}>Add part</Button> : undefined
          }
        />
      ) : (
        <>
          <Table caption="Parts and stock levels">
            <THead>
              <TR>
                <TH>Part</TH>
                <TH>Category</TH>
                <TH className="text-right">Stock</TH>
                <TH className="text-right">Reorder at</TH>
                <TH className="text-right">Cost</TH>
                <TH className="text-right">Price</TH>
                <TH className="text-right">Actions</TH>
              </TR>
            </THead>
            <TBody>
              {parts.data?.items.map((part) => {
                const low = Number.parseFloat(part.stock_qty) <= Number.parseFloat(part.reorder_level);
                return (
                  <TR key={part.id}>
                    <TD>
                      <div className="font-medium">{part.name}</div>
                      <div className="text-xs text-[var(--muted-foreground)]">
                        {part.sku}
                        {part.brand ? ` · ${part.brand}` : ""}
                      </div>
                    </TD>
                    <TD className="text-[var(--muted-foreground)]">{part.category ?? "—"}</TD>
                    <TD className="text-right tabular-nums">
                      <span className={low ? "font-medium text-[var(--destructive)]" : ""}>
                        {qty(part.stock_qty)}
                      </span>
                      {low && (
                        <span className="ml-2 rounded-full bg-[color-mix(in_oklab,var(--destructive)_14%,transparent)] px-2 py-0.5 text-[11px] font-medium text-[var(--destructive)]">
                          Low
                        </span>
                      )}
                    </TD>
                    <TD className="text-right tabular-nums text-[var(--muted-foreground)]">
                      {qty(part.reorder_level)}
                    </TD>
                    <TD className="text-right tabular-nums">{money(part.cost, currency)}</TD>
                    <TD className="text-right tabular-nums">{money(part.price, currency)}</TD>
                    <TD className="text-right">
                      {canWrite && (
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Adjust stock for ${part.name}`}
                            onClick={() => {
                              setAdjusting(part);
                              setAdjust({ direction: "in", quantity: "", note: "" });
                            }}
                          >
                            <PackagePlus className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Edit ${part.name}`}
                            onClick={() => openEdit(part)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Archive ${part.name}`}
                            onClick={() => setArchiving(part)}
                          >
                            <Archive className="h-4 w-4" />
                          </Button>
                        </div>
                      )}
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
          <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
        </>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title={editing ? `Edit ${editing.name}` : "Add part"}
          description={
            editing
              ? "Update catalogue details. Stock changes are recorded separately."
              : "Catalogue a part and optionally record opening stock."
          }
        >
          <form onSubmit={save} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name" htmlFor="part-name">
                <Input
                  id="part-name"
                  value={form.name}
                  onChange={(e) => set("name", e.target.value)}
                  required
                />
              </Field>
              <Field label="SKU" htmlFor="part-sku" hint="Leave blank to auto-generate">
                <Input id="part-sku" value={form.sku} onChange={(e) => set("sku", e.target.value)} />
              </Field>
              <Field label="Category" htmlFor="part-category">
                <Input
                  id="part-category"
                  value={form.category}
                  onChange={(e) => set("category", e.target.value)}
                  placeholder="Brakes"
                />
              </Field>
              <Field label="Brand" htmlFor="part-brand">
                <Input id="part-brand" value={form.brand} onChange={(e) => set("brand", e.target.value)} />
              </Field>
              <Field label="Supplier" htmlFor="part-supplier">
                <Input
                  id="part-supplier"
                  value={form.supplier}
                  onChange={(e) => set("supplier", e.target.value)}
                />
              </Field>
              <Field label="Location" htmlFor="part-location">
                <Input
                  id="part-location"
                  value={form.location}
                  onChange={(e) => set("location", e.target.value)}
                  placeholder="Shelf B-3"
                />
              </Field>
              <Field label="Unit cost" htmlFor="part-cost">
                <Input
                  id="part-cost"
                  type="number"
                  min={0}
                  step="0.01"
                  value={form.cost}
                  onChange={(e) => set("cost", e.target.value)}
                />
              </Field>
              <Field label="Sell price" htmlFor="part-price">
                <Input
                  id="part-price"
                  type="number"
                  min={0}
                  step="0.01"
                  value={form.price}
                  onChange={(e) => set("price", e.target.value)}
                />
              </Field>
              {!editing && (
                <Field label="Opening stock" htmlFor="part-stock">
                  <Input
                    id="part-stock"
                    type="number"
                    min={0}
                    step="0.01"
                    value={form.stock_qty}
                    onChange={(e) => set("stock_qty", e.target.value)}
                  />
                </Field>
              )}
              <Field label="Reorder level" htmlFor="part-reorder">
                <Input
                  id="part-reorder"
                  type="number"
                  min={0}
                  step="0.01"
                  value={form.reorder_level}
                  onChange={(e) => set("reorder_level", e.target.value)}
                />
              </Field>
            </div>
            <Field label="Notes" htmlFor="part-notes">
              <Textarea
                id="part-notes"
                value={form.notes}
                onChange={(e) => set("notes", e.target.value)}
                rows={2}
              />
            </Field>
            {formError && <p className="text-sm text-[var(--destructive)]">{formError}</p>}
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                {editing ? "Save changes" : "Add part"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={adjusting !== null} onOpenChange={(value) => !value && setAdjusting(null)}>
        <DialogContent
          title={adjusting ? `Adjust stock — ${adjusting.name}` : "Adjust stock"}
          description={
            adjusting
              ? `Current stock: ${adjusting.stock_qty}. Every change is recorded in the ledger.`
              : undefined
          }
        >
          <form onSubmit={saveAdjust} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Direction" htmlFor="adjust-direction">
                <Select
                  id="adjust-direction"
                  value={adjust.direction}
                  onChange={(e) => setAdjust((prev) => ({ ...prev, direction: e.target.value }))}
                >
                  <option value="in">Receive stock</option>
                  <option value="out">Adjust out</option>
                </Select>
              </Field>
              <Field label="Quantity" htmlFor="adjust-qty">
                <Input
                  id="adjust-qty"
                  type="number"
                  min={0.01}
                  step="0.01"
                  value={adjust.quantity}
                  onChange={(e) => setAdjust((prev) => ({ ...prev, quantity: e.target.value }))}
                  required
                />
              </Field>
            </div>
            <Field label="Note" htmlFor="adjust-note">
              <Input
                id="adjust-note"
                value={adjust.note}
                onChange={(e) => setAdjust((prev) => ({ ...prev, note: e.target.value }))}
                placeholder="Delivery, count correction…"
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setAdjusting(null)}>
                Cancel
              </Button>
              <Button type="submit" loading={adjustingBusy}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={archiving !== null} onOpenChange={(value) => !value && setArchiving(null)}>
        <DialogContent
          title={archiving ? `Archive ${archiving.name}?` : "Archive part"}
          description="Archived parts stay in historical orders and movements but can no longer be added to new work."
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setArchiving(null)}>
              Cancel
            </Button>
            <Button variant="destructive" loading={archiveBusy} onClick={archive}>
              Archive
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
