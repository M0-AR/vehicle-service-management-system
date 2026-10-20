"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Link2, Plus, Printer, Receipt, Star, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { InspectionPanel } from "@/components/inspection-panel";
import { PageHeader } from "@/components/page";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/fields";
import { ErrorState, LoadingBlock } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBranding } from "@/lib/branding";
import { formatDateTime, money, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type {
  Customer,
  Invoice,
  Location,
  Order,
  Page,
  Part,
  ReviewRequest,
  ShareLink,
  User,
  Vehicle,
} from "@/lib/types";

const TRANSITIONS: Record<string, string[]> = {
  scheduled: ["in_progress", "cancelled"],
  in_progress: ["awaiting_parts", "completed", "cancelled"],
  awaiting_parts: ["in_progress", "cancelled"],
  completed: [],
  invoiced: [],
  cancelled: [],
};

const TRANSITION_LABELS: Record<string, string> = {
  in_progress: "Start work",
  awaiting_parts: "Request parts",
  completed: "Mark completed",
  cancelled: "Cancel order",
};

function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const { user, hasFeature } = useAuth();
  const { currency } = useBranding();
  const role = user?.role ?? "";
  const canManage = ["owner", "admin", "manager"].includes(role);
  const canWork = ["owner", "admin", "manager", "mechanic"].includes(role);
  const canInvoice = ["owner", "admin", "manager"].includes(role);

  const { data: order, error, isLoading, mutate } = useApi<Order>(`/service-orders/${id}`);
  const vehicle = useApi<Vehicle>(order?.vehicle_id ? `/vehicles/${order.vehicle_id}` : null);
  const customer = useApi<Customer>(order?.customer_id ? `/customers/${order.customer_id}` : null);
  const staff = useApi<{ items: User[] }>(canManage ? "/staff?page_size=100" : null);
  const locations = useApi<Location[]>("/locations");
  const inventoryParts = useApi<Page<Part>>(
    hasFeature("inventory") ? "/inventory/parts?page_size=100" : null,
  );

  const [busy, setBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);

  const [itemKind, setItemKind] = useState("labor");
  const [itemPartId, setItemPartId] = useState("");
  const [itemDescription, setItemDescription] = useState("");
  const [itemQty, setItemQty] = useState("1");
  const [itemPrice, setItemPrice] = useState("");
  const [itemBusy, setItemBusy] = useState(false);

  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState({
    description: "",
    location_id: "",
    priority: "normal",
    scheduled_at: "",
    mechanic_id: "",
    estimated_cost: "",
    odometer: "",
    notes: "",
  });
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [invoiceBusy, setInvoiceBusy] = useState(false);
  const [share, setShare] = useState<ShareLink | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [review, setReview] = useState<ReviewRequest | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);

  if (error) return <ErrorState message="Could not load this service order" retry={() => mutate()} />;
  if (isLoading && !order) return <LoadingBlock label="Loading order" />;
  if (!order) return null;

  const terminal = order.status === "invoiced" || order.status === "cancelled";
  const transitions = TRANSITIONS[order.status] ?? [];

  async function transition(status: string) {
    setBusy(true);
    try {
      await api(`/service-orders/${id}/status`, { body: { status } });
      toast.success(`Order ${titleCase(status).toLowerCase()}`);
      setConfirmCancel(false);
      mutate();
      if (hasFeature("inventory")) inventoryParts.mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function addItem(event: React.FormEvent) {
    event.preventDefault();
    setItemBusy(true);
    try {
      await api(`/service-orders/${id}/items`, {
        body: {
          kind: itemKind,
          part_id: itemKind === "part" && itemPartId ? itemPartId : null,
          description: itemDescription.trim(),
          quantity: Number.parseFloat(itemQty) || 1,
          unit_price: Number.parseFloat(itemPrice) || 0,
        },
      });
      toast.success("Item added");
      setItemPartId("");
      setItemDescription("");
      setItemQty("1");
      setItemPrice("");
      mutate();
      if (hasFeature("inventory")) inventoryParts.mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setItemBusy(false);
    }
  }

  async function removeItem(itemId: string) {
    try {
      await api(`/service-orders/${id}/items/${itemId}`, { method: "DELETE" });
      toast.success("Item removed");
      mutate();
      if (hasFeature("inventory")) inventoryParts.mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  function openEdit() {
    if (!order) return;
    setEditForm({
      description: order.description,
      location_id: order.location_id ?? "",
      priority: order.priority,
      scheduled_at: toLocalInput(order.scheduled_at),
      mechanic_id: order.mechanic_id ?? "",
      estimated_cost: order.estimated_cost ?? "",
      odometer: order.odometer ? String(order.odometer) : "",
      notes: order.notes ?? "",
    });
    setEditError(null);
    setEditOpen(true);
  }

  async function saveEdit(event: React.FormEvent) {
    event.preventDefault();
    setEditBusy(true);
    setEditError(null);
    try {
      await api(`/service-orders/${id}`, {
        method: "PATCH",
        body: {
          description: editForm.description.trim(),
          location_id: editForm.location_id || null,
          priority: editForm.priority,
          scheduled_at: editForm.scheduled_at
            ? new Date(editForm.scheduled_at).toISOString()
            : null,
          mechanic_id: editForm.mechanic_id || null,
          estimated_cost: editForm.estimated_cost
            ? Number.parseFloat(editForm.estimated_cost)
            : null,
          odometer: editForm.odometer ? Number.parseInt(editForm.odometer, 10) : null,
          notes: editForm.notes.trim() || null,
        },
      });
      toast.success("Order updated");
      setEditOpen(false);
      mutate();
    } catch (err) {
      setEditError(errorMessage(err));
    } finally {
      setEditBusy(false);
    }
  }

  async function shareOrder() {
    setShareBusy(true);
    try {
      const link = await api<ShareLink>(`/service-orders/${id}/share`, { method: "POST" });
      setShare(link);
      const url = `${window.location.origin}${link.url_path}`;
      try {
        await navigator.clipboard.writeText(url);
        toast.success("Status link copied");
      } catch {
        window.prompt("Copy this status link", url);
      }
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setShareBusy(false);
    }
  }

  async function copyShare() {
    if (!share) return;
    const url = `${window.location.origin}${share.url_path}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Link copied");
    } catch {
      window.prompt("Copy this status link", url);
    }
  }

  async function revokeShare() {
    setShareBusy(true);
    try {
      await api(`/service-orders/${id}/share`, { method: "DELETE" });
      setShare(null);
      toast.success("Status link revoked");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setShareBusy(false);
    }
  }

  async function requestReview() {
    setReviewBusy(true);
    try {
      const link = await api<ReviewRequest>(`/service-orders/${id}/review-request`, {
        method: "POST",
      });
      setReview(link);
      const url = `${window.location.origin}${link.url_path ?? ""}`;
      try {
        await navigator.clipboard.writeText(url);
        toast.success("Review link copied");
      } catch {
        window.prompt("Copy this review link", url);
      }
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setReviewBusy(false);
    }
  }

  async function createInvoice() {
    setInvoiceBusy(true);
    try {
      await api<Invoice>("/invoices/from-order", {
        body: { order_id: id, due_days: 14 },
      });
      toast.success("Invoice created");
      router.push("/app/invoices");
    } catch (err) {
      toast.error(errorMessage(err));
      setInvoiceBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="print:hidden">
        <Link
          href="/app/orders"
          className="inline-flex items-center gap-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          All service orders
        </Link>
      </div>

      <PageHeader
        title={order.number}
        description={`Created ${formatDateTime(order.created_at)}`}
      >
        <StatusBadge status={order.priority} kind="priority" />
        <StatusBadge status={order.status} kind="order" />
      </PageHeader>

      <div className="flex flex-wrap gap-2 print:hidden">
        {canWork &&
          transitions
            .filter((s) => s !== "cancelled")
            .map((s) => (
              <Button key={s} onClick={() => transition(s)} loading={busy} disabled={busy}>
                {TRANSITION_LABELS[s] ?? titleCase(s)}
              </Button>
            ))}
        {canWork && transitions.includes("cancelled") && (
          <Button variant="secondary" onClick={() => setConfirmCancel(true)} disabled={busy}>
            Cancel order
          </Button>
        )}
        {canInvoice && order.status === "completed" && (
          <Button onClick={createInvoice} loading={invoiceBusy}>
            <Receipt className="h-4 w-4" aria-hidden="true" />
            Create invoice
          </Button>
        )}
        {canManage && !terminal && (
          <Button variant="secondary" onClick={openEdit}>
            Edit details
          </Button>
        )}
        {!terminal && canWork && (
          <Button variant="secondary" onClick={shareOrder} loading={shareBusy}>
            <Link2 className="h-4 w-4" aria-hidden="true" />
            Share status link
          </Button>
        )}
        {(order.status === "completed" || order.status === "invoiced") &&
          canManage &&
          hasFeature("review_requests") && (
            <Button variant="secondary" onClick={requestReview} loading={reviewBusy}>
              <Star className="h-4 w-4" aria-hidden="true" />
              Request review
            </Button>
          )}
        <Button variant="secondary" onClick={() => window.print()}>
          <Printer className="h-4 w-4" aria-hidden="true" />
          Print
        </Button>
      </div>

      {review?.url_path && (
        <Card className="print:hidden">
          <CardContent className="flex flex-col gap-3 pt-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-medium">Review request</p>
              <p className="truncate text-sm text-[var(--muted-foreground)]">
                {typeof window !== "undefined"
                  ? `${window.location.origin}${review.url_path}`
                  : review.url_path}
              </p>
            </div>
            <Button
              variant="secondary"
              onClick={async () => {
                const url = `${window.location.origin}${review.url_path}`;
                try {
                  await navigator.clipboard.writeText(url);
                  toast.success("Review link copied");
                } catch {
                  window.prompt("Copy this review link", url);
                }
              }}
            >
              Copy
            </Button>
          </CardContent>
        </Card>
      )}

      {share && (
        <Card className="print:hidden">
          <CardContent className="flex flex-col gap-3 pt-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-medium">Customer status link</p>
              <p className="truncate text-sm text-[var(--muted-foreground)]">
                {typeof window !== "undefined"
                  ? `${window.location.origin}${share.url_path}`
                  : share.url_path}
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={copyShare}>
                Copy
              </Button>
              <Button variant="secondary" onClick={revokeShare} loading={shareBusy}>
                Revoke
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Job</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="whitespace-pre-wrap text-sm">{order.description}</p>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-[var(--muted-foreground)]">Vehicle</dt>
                <dd className="font-medium">
                  {vehicle.data
                    ? `${vehicle.data.plate_number} — ${vehicle.data.make} ${vehicle.data.model}`
                    : "…"}
                </dd>
              </div>
              <div>
                <dt className="text-[var(--muted-foreground)]">Customer</dt>
                <dd className="font-medium">{customer.data?.name ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-[var(--muted-foreground)]">Scheduled for</dt>
                <dd>{formatDateTime(order.scheduled_at)}</dd>
              </div>
              <div>
                <dt className="text-[var(--muted-foreground)]">Odometer</dt>
                <dd>{order.odometer !== null ? `${order.odometer} km` : "—"}</dd>
              </div>
              <div>
                <dt className="text-[var(--muted-foreground)]">Estimated cost</dt>
                <dd>{money(order.estimated_cost, currency)}</dd>
              </div>
              <div>
                <dt className="text-[var(--muted-foreground)]">Completed</dt>
                <dd>{formatDateTime(order.completed_at)}</dd>
              </div>
            </dl>
            {order.notes && (
              <div>
                <p className="text-sm text-[var(--muted-foreground)]">Notes</p>
                <p className="whitespace-pre-wrap text-sm">{order.notes}</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Totals</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-[var(--muted-foreground)]">Labour</dt>
                <dd>{money(order.totals.labor ?? "0", currency)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-[var(--muted-foreground)]">Parts</dt>
                <dd>{money(order.totals.parts ?? "0", currency)}</dd>
              </div>
              <div className="flex justify-between border-t border-[var(--border)] pt-2 text-base font-semibold">
                <dt>Total</dt>
                <dd>{money(order.totals.total ?? "0", currency)}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Line items</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Table caption="Order line items" className="rounded-lg">
            <THead>
              <TR>
                <TH>Kind</TH>
                <TH>Description</TH>
                <TH className="text-right">Qty</TH>
                <TH className="text-right">Unit price</TH>
                <TH className="text-right">Total</TH>
                <TH><span className="sr-only">Remove</span></TH>
              </TR>
            </THead>
            <TBody>
              {order.items.map((item) => (
                <TR key={item.id}>
                  <TD className="capitalize text-[var(--muted-foreground)]">{item.kind}</TD>
                  <TD>{item.description}</TD>
                  <TD className="text-right">{item.quantity}</TD>
                  <TD className="text-right">{money(item.unit_price, currency)}</TD>
                  <TD className="text-right font-medium">{money(item.total, currency)}</TD>
                  <TD className="w-12 text-right">
                    {!terminal && canWork && (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove ${item.description}`}
                        onClick={() => removeItem(item.id)}
                      >
                        <Trash2 className="h-4 w-4 text-[var(--destructive)]" aria-hidden="true" />
                      </Button>
                    )}
                  </TD>
                </TR>
              ))}
              {order.items.length === 0 && (
                <TR>
                  <TD colSpan={6} className="py-6 text-center text-[var(--muted-foreground)]">
                    No items yet.
                  </TD>
                </TR>
              )}
            </TBody>
          </Table>

          {!terminal && canWork && (
            <form
              onSubmit={addItem}
              className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-[7rem_10rem_1fr_5rem_7rem_auto]"
            >
              <Field label="Kind" htmlFor="li-kind">
                <Select
                  id="li-kind"
                  value={itemKind}
                  onChange={(e) => {
                    setItemKind(e.target.value);
                    setItemPartId("");
                    setItemDescription("");
                    setItemPrice("");
                  }}
                >
                  <option value="labor">Labor</option>
                  <option value="part">Part</option>
                </Select>
              </Field>
              {itemKind === "part" && hasFeature("inventory") && (
                <Field label="From stock" htmlFor="li-part">
                  <Select
                    id="li-part"
                    value={itemPartId}
                    onChange={(e) => {
                      const partId = e.target.value;
                      setItemPartId(partId);
                      const part = inventoryParts.data?.items.find((p) => p.id === partId);
                      if (part) {
                        setItemDescription(part.name);
                        setItemPrice(part.price);
                      }
                    }}
                  >
                    <option value="">No stock link</option>
                    {inventoryParts.data?.items.map((part) => (
                      <option key={part.id} value={part.id}>
                        {part.name} · {Number(part.stock_qty).toLocaleString()} in stock
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              <Field label="Description" htmlFor="li-description">
                <Input
                  id="li-description"
                  value={itemDescription}
                  onChange={(e) => setItemDescription(e.target.value)}
                  required
                />
              </Field>
              <Field label="Qty" htmlFor="li-qty">
                <Input
                  id="li-qty"
                  type="number"
                  min={0.1}
                  step="0.1"
                  value={itemQty}
                  onChange={(e) => setItemQty(e.target.value)}
                />
              </Field>
              <Field label="Unit price" htmlFor="li-price">
                <Input
                  id="li-price"
                  type="number"
                  min={0}
                  step="0.01"
                  value={itemPrice}
                  onChange={(e) => setItemPrice(e.target.value)}
                  required
                />
              </Field>
              <Button type="submit" loading={itemBusy}>
                <Plus className="h-4 w-4" aria-hidden="true" />
                Add
              </Button>
            </form>
          )}
        </CardContent>
      </Card>

      <InspectionPanel orderId={id} canEdit={canWork} featureEnabled={hasFeature("dvi")} />

      <Dialog open={confirmCancel} onOpenChange={setConfirmCancel}>
        <DialogContent
          title="Cancel this order?"
          description="The order will be closed as cancelled. This can not be undone."
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirmCancel(false)}>
              Keep order
            </Button>
            <Button variant="destructive" onClick={() => transition("cancelled")} loading={busy}>
              Cancel order
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent title="Edit order" description="Update the job details." wide>
          <form onSubmit={saveEdit} className="space-y-4">
            {editError && (
              <div role="alert" className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]">
                {editError}
              </div>
            )}
            <Field label="Description" htmlFor="e-description" required>
              <Textarea
                id="e-description"
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                required
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Priority" htmlFor="e-priority">
                <Select
                  id="e-priority"
                  value={editForm.priority}
                  onChange={(e) => setEditForm({ ...editForm, priority: e.target.value })}
                >
                  {["low", "normal", "high", "urgent"].map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Scheduled for" htmlFor="e-scheduled">
                <Input
                  id="e-scheduled"
                  type="datetime-local"
                  value={editForm.scheduled_at}
                  onChange={(e) => setEditForm({ ...editForm, scheduled_at: e.target.value })}
                />
              </Field>
              <Field label="Odometer (km)" htmlFor="e-odometer">
                <Input
                  id="e-odometer"
                  type="number"
                  min={0}
                  value={editForm.odometer}
                  onChange={(e) => setEditForm({ ...editForm, odometer: e.target.value })}
                />
              </Field>
              <Field label="Estimated cost" htmlFor="e-estimate">
                <Input
                  id="e-estimate"
                  type="number"
                  min={0}
                  step="0.01"
                  value={editForm.estimated_cost}
                  onChange={(e) => setEditForm({ ...editForm, estimated_cost: e.target.value })}
                />
              </Field>
              {canManage && (locations.data?.length ?? 0) > 0 && (
                <Field label="Location" htmlFor="e-location">
                  <Select
                    id="e-location"
                    value={editForm.location_id}
                    onChange={(e) => setEditForm({ ...editForm, location_id: e.target.value })}
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
              {canManage && (
                <Field label="Assign to" htmlFor="e-mechanic">
                  <Select
                    id="e-mechanic"
                    value={editForm.mechanic_id}
                    onChange={(e) => setEditForm({ ...editForm, mechanic_id: e.target.value })}
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
            <Field label="Notes" htmlFor="e-notes">
              <Textarea
                id="e-notes"
                value={editForm.notes}
                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={editBusy}>
                Save changes
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
