"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Link2, Plus, Printer, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { EstimateStatusBadge } from "@/components/estimate-status";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/fields";
import { ErrorState, LoadingBlock } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBranding } from "@/lib/branding";
import { formatDateTime, money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Customer, Estimate, ShareLink, Vehicle } from "@/lib/types";

export default function EstimateDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const { user } = useAuth();
  const { currency } = useBranding();
  const role = user?.role ?? "";
  const canEdit = ["owner", "admin", "manager", "mechanic"].includes(role);
  const canDelete = ["owner", "admin", "manager"].includes(role);

  const { data: estimate, error, isLoading, mutate } = useApi<Estimate>(`/estimates/${id}`);
  const vehicle = useApi<Vehicle>(
    estimate?.vehicle_id ? `/vehicles/${estimate.vehicle_id}` : null,
  );
  const customer = useApi<Customer>(
    estimate?.customer_id ? `/customers/${estimate.customer_id}` : null,
  );

  const [busy, setBusy] = useState(false);
  const [share, setShare] = useState<ShareLink | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [itemKind, setItemKind] = useState("labor");
  const [itemDescription, setItemDescription] = useState("");
  const [itemQty, setItemQty] = useState("1");
  const [itemPrice, setItemPrice] = useState("");
  const [itemBusy, setItemBusy] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState({ description: "", notes: "" });
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (error) return <ErrorState message="Could not load this estimate" retry={() => mutate()} />;
  if (isLoading && !estimate) return <LoadingBlock label="Loading estimate" />;
  if (!estimate) return null;

  const editable = estimate.status === "draft";
  const shareable = estimate.status === "draft" || estimate.status === "sent";

  async function addItem(event: React.FormEvent) {
    event.preventDefault();
    setItemBusy(true);
    try {
      await api(`/estimates/${id}/items`, {
        body: {
          kind: itemKind,
          description: itemDescription.trim(),
          quantity: Number.parseFloat(itemQty) || 1,
          unit_price: Number.parseFloat(itemPrice) || 0,
        },
      });
      toast.success("Line item added");
      setItemDescription("");
      setItemQty("1");
      setItemPrice("");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setItemBusy(false);
    }
  }

  async function removeItem(itemId: string) {
    try {
      await api(`/estimates/${id}/items/${itemId}`, { method: "DELETE" });
      toast.success("Line item removed");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function sendEstimate() {
    setBusy(true);
    try {
      const link = await api<ShareLink>(`/estimates/${id}/send`, { method: "POST" });
      setShare(link);
      toast.success("Approval link ready");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    if (!share) return;
    const url = `${window.location.origin}${share.url_path}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Link copied");
    } catch {
      window.prompt("Copy this link", url);
    }
  }

  async function revokeShare() {
    setShareBusy(true);
    try {
      await api(`/estimates/${id}/share`, { method: "DELETE" });
      setShare(null);
      toast.success("Approval link revoked");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setShareBusy(false);
    }
  }

  function openEdit() {
    if (!estimate) return;
    setEditForm({ description: estimate.description, notes: estimate.notes ?? "" });
    setEditError(null);
    setEditOpen(true);
  }

  async function saveEdit(event: React.FormEvent) {
    event.preventDefault();
    setEditBusy(true);
    setEditError(null);
    try {
      await api(`/estimates/${id}`, {
        method: "PATCH",
        body: {
          description: editForm.description.trim(),
          notes: editForm.notes.trim() || null,
        },
      });
      toast.success("Estimate updated");
      setEditOpen(false);
      mutate();
    } catch (err) {
      setEditError(errorMessage(err));
    } finally {
      setEditBusy(false);
    }
  }

  async function deleteEstimate() {
    setBusy(true);
    try {
      await api(`/estimates/${id}`, { method: "DELETE" });
      toast.success("Estimate deleted");
      router.push("/app/estimates");
    } catch (err) {
      toast.error(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="print:hidden">
        <Link
          href="/app/estimates"
          className="inline-flex items-center gap-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          All estimates
        </Link>
      </div>

      <PageHeader
        title={estimate.number}
        description={`Created ${formatDateTime(estimate.created_at)}`}
      >
        <EstimateStatusBadge status={estimate.status} />
      </PageHeader>

      <div className="flex flex-wrap gap-2 print:hidden">
        {shareable && (
          <Button onClick={sendEstimate} loading={busy}>
            <Send className="h-4 w-4" aria-hidden="true" />
            {estimate.status === "sent" ? "Reissue link" : "Send for approval"}
          </Button>
        )}
        {share && (
          <>
            <Button variant="secondary" onClick={copyLink}>
              <Link2 className="h-4 w-4" aria-hidden="true" />
              Copy link
            </Button>
            <Button variant="secondary" onClick={revokeShare} loading={shareBusy}>
              Revoke link
            </Button>
          </>
        )}
        {canEdit && editable && (
          <Button variant="secondary" onClick={openEdit}>
            Edit details
          </Button>
        )}
        <Button variant="secondary" onClick={() => window.print()}>
          <Printer className="h-4 w-4" aria-hidden="true" />
          Print
        </Button>
        {canDelete && editable && (
          <Button variant="secondary" onClick={() => setConfirmDelete(true)}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            Delete
          </Button>
        )}
      </div>

      {share && (
        <Card className="print:hidden">
          <CardContent className="flex flex-col gap-3 pt-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-medium">Customer approval link</p>
              <p className="truncate text-sm text-[var(--muted-foreground)]">
                {typeof window !== "undefined"
                  ? `${window.location.origin}${share.url_path}`
                  : share.url_path}
              </p>
            </div>
            <Button variant="secondary" onClick={copyLink}>
              Copy
            </Button>
          </CardContent>
        </Card>
      )}

      {estimate.converted_order_id && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm">
              This estimate was approved and converted to{" "}
              <Link
                href={`/app/orders/${estimate.converted_order_id}`}
                className="font-medium text-[var(--brand-text)] hover:underline"
              >
                a service order
              </Link>
              .
            </p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Quote</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="whitespace-pre-wrap text-sm">{estimate.description}</p>
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
                <dt className="text-[var(--muted-foreground)]">Sent</dt>
                <dd>{formatDateTime(estimate.sent_at)}</dd>
              </div>
              <div>
                <dt className="text-[var(--muted-foreground)]">Answered</dt>
                <dd>
                  {formatDateTime(estimate.responded_at)}
                  {estimate.responded_by_name ? ` · ${estimate.responded_by_name}` : ""}
                </dd>
              </div>
            </dl>
            {estimate.notes && (
              <div>
                <p className="text-sm text-[var(--muted-foreground)]">Notes</p>
                <p className="whitespace-pre-wrap text-sm">{estimate.notes}</p>
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
                <dd>{money(estimate.totals.labor ?? "0", currency)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-[var(--muted-foreground)]">Parts</dt>
                <dd>{money(estimate.totals.parts ?? "0", currency)}</dd>
              </div>
              <div className="flex justify-between border-t border-[var(--border)] pt-2 text-base font-semibold">
                <dt>Total</dt>
                <dd>{money(estimate.totals.total ?? "0", currency)}</dd>
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
          <Table caption="Estimate line items" className="rounded-lg">
            <THead>
              <TR>
                <TH>Kind</TH>
                <TH>Description</TH>
                <TH className="text-right">Qty</TH>
                <TH className="text-right">Unit price</TH>
                <TH className="text-right">Total</TH>
                <TH className="print:hidden">
                  <span className="sr-only">Remove</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {estimate.items.map((item) => (
                <TR key={item.id}>
                  <TD className="capitalize text-[var(--muted-foreground)]">{item.kind}</TD>
                  <TD>{item.description}</TD>
                  <TD className="text-right">{item.quantity}</TD>
                  <TD className="text-right">{money(item.unit_price, currency)}</TD>
                  <TD className="text-right font-medium">{money(item.total, currency)}</TD>
                  <TD className="w-12 text-right print:hidden">
                    {editable && canEdit && (
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
              {estimate.items.length === 0 && (
                <TR>
                  <TD colSpan={6} className="py-6 text-center text-[var(--muted-foreground)]">
                    No line items yet — add labour and parts below.
                  </TD>
                </TR>
              )}
            </TBody>
          </Table>

          {editable && canEdit && (
            <form
              onSubmit={addItem}
              className="grid items-end gap-3 sm:grid-cols-[8rem_1fr_6rem_8rem_auto] print:hidden"
            >
              <Field label="Kind" htmlFor="est-kind">
                <Select
                  id="est-kind"
                  value={itemKind}
                  onChange={(e) => setItemKind(e.target.value)}
                >
                  <option value="labor">Labor</option>
                  <option value="part">Part</option>
                </Select>
              </Field>
              <Field label="Description" htmlFor="est-item-description">
                <Input
                  id="est-item-description"
                  value={itemDescription}
                  onChange={(e) => setItemDescription(e.target.value)}
                  required
                />
              </Field>
              <Field label="Qty" htmlFor="est-item-qty">
                <Input
                  id="est-item-qty"
                  type="number"
                  min={0.1}
                  step="0.1"
                  value={itemQty}
                  onChange={(e) => setItemQty(e.target.value)}
                />
              </Field>
              <Field label="Unit price" htmlFor="est-item-price">
                <Input
                  id="est-item-price"
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

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent title="Edit estimate" description="Update the quote details." wide>
          <form onSubmit={saveEdit} className="space-y-4">
            {editError && (
              <div
                role="alert"
                className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]"
              >
                {editError}
              </div>
            )}
            <Field label="Work to quote" htmlFor="est-edit-description" required>
              <Textarea
                id="est-edit-description"
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                required
              />
            </Field>
            <Field label="Notes for the customer" htmlFor="est-edit-notes">
              <Textarea
                id="est-edit-notes"
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

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent
          title="Delete this estimate?"
          description="Only drafts can be deleted. This cannot be undone."
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirmDelete(false)}>
              Keep estimate
            </Button>
            <Button variant="destructive" onClick={deleteEstimate} loading={busy}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
