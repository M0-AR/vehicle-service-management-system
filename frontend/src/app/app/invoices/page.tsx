"use client";

import { useMemo, useState } from "react";
import { CreditCard, FilePlus2, MoreHorizontal, Printer, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { FilterChips, PageHeader, Pager, SearchInput } from "@/components/page";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown";
import { Field, Select } from "@/components/ui/fields";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBranding } from "@/lib/branding";
import { formatDate, money, titleCase } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import type { Invoice, InvoiceListItem, OrderListItem, Page } from "@/lib/types";

const PAGE_SIZE = 25;

const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "draft", label: "Draft" },
  { value: "sent", label: "Sent" },
  { value: "paid", label: "Paid" },
  { value: "overdue", label: "Overdue" },
  { value: "void", label: "Void" },
];

export default function InvoicesPage() {
  const { user } = useAuth();
  const { currency } = useBranding();
  const role = user?.role ?? "";
  const canManage = ["owner", "admin", "manager"].includes(role);
  const canDelete = ["owner", "admin"].includes(role);

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

  const { data, error, isLoading, mutate } = useApi<Page<InvoiceListItem>>(`/invoices?${query}`);

  const [viewing, setViewing] = useState<Invoice | null>(null);
  const [viewBusy, setViewBusy] = useState(false);
  const [payBusy, setPayBusy] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<InvoiceListItem | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [fromOrderOpen, setFromOrderOpen] = useState(false);
  const [orderId, setOrderId] = useState("");
  const [fromOrderBusy, setFromOrderBusy] = useState(false);
  const [fromOrderError, setFromOrderError] = useState<string | null>(null);

  const completedOrders = useApi<Page<OrderListItem>>(
    fromOrderOpen ? "/service-orders?status=completed&page_size=100" : null,
  );

  async function openView(id: string) {
    setViewBusy(true);
    try {
      const invoice = await api<Invoice>(`/invoices/${id}`);
      setViewing(invoice);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setViewBusy(false);
    }
  }

  async function createPaymentLink() {
    if (!viewing) return;
    setPayBusy(true);
    setPayError(null);
    try {
      const link = await api<{ url: string; message: string }>(
        `/invoices/${viewing.id}/payment-link`,
        { method: "POST" },
      );
      setViewing({ ...viewing, payment_url: link.url, payment_provider: "stripe" });
      try {
        await navigator.clipboard.writeText(link.url);
        toast.success("Payment link copied");
      } catch {
        window.prompt("Copy this payment link", link.url);
      }
      mutate();
    } catch (err) {
      setPayError(errorMessage(err));
    } finally {
      setPayBusy(false);
    }
  }

  async function changeStatus(id: string, next: string) {
    try {
      await api(`/invoices/${id}/status`, { body: { status: next } });
      toast.success(`Invoice marked ${next}`);
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api(`/invoices/${deleting.id}`, { method: "DELETE" });
      toast.success(`Deleted ${deleting.number}`);
      setDeleting(null);
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setDeleteBusy(false);
    }
  }

  async function createFromOrder(event: React.FormEvent) {
    event.preventDefault();
    setFromOrderBusy(true);
    setFromOrderError(null);
    try {
      await api<Invoice>("/invoices/from-order", { body: { order_id: orderId, due_days: 14 } });
      toast.success("Invoice created");
      setFromOrderOpen(false);
      setOrderId("");
      mutate();
    } catch (err) {
      setFromOrderError(errorMessage(err));
    } finally {
      setFromOrderBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Invoices" description="Billing for completed work.">
        {canManage && (
          <Button onClick={() => setFromOrderOpen(true)}>
            <FilePlus2 className="h-4 w-4" aria-hidden="true" />
            Invoice from order
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
          placeholder="Search number or customer…"
          label="Search invoices"
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

      {error && <ErrorState message="Could not load invoices" retry={() => mutate()} />}
      {isLoading && !data && <TableSkeleton />}

      {data && data.items.length === 0 && (
        <EmptyState
          title="No invoices found"
          description={
            q || status !== "all"
              ? "Try a different search or filter."
              : "Create one from a completed service order."
          }
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <Table caption="Invoices">
            <THead>
              <TR>
                <TH>Invoice</TH>
                <TH>Customer</TH>
                <TH>Status</TH>
                <TH className="hidden sm:table-cell">Issued</TH>
                <TH className="hidden sm:table-cell">Due</TH>
                <TH numeric>Total</TH>
                <TH><span className="sr-only">Actions</span></TH>
              </TR>
            </THead>
            <TBody>
              {data.items.map((inv) => (
                <TR key={inv.id}>
                  <TD className="font-medium">{inv.number}</TD>
                  <TD className="text-[var(--muted-foreground)]">{inv.customer_name ?? "—"}</TD>
                  <TD>
                    <StatusBadge status={inv.status} kind="invoice" />
                  </TD>
                  <TD className="hidden text-[var(--muted-foreground)] sm:table-cell">
                    {formatDate(inv.issued_at)}
                  </TD>
                  <TD className="hidden text-[var(--muted-foreground)] sm:table-cell">
                    {formatDate(inv.due_at)}
                  </TD>
                  <TD numeric className="font-medium">{money(inv.total, inv.currency || currency)}</TD>
                  <TD className="w-12 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Actions for ${inv.number}`}
                          disabled={viewBusy}
                        >
                          <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        <DropdownMenuItem onSelect={() => openView(inv.id)}>View</DropdownMenuItem>
                        {canManage && inv.status !== "paid" && inv.status !== "void" && (
                          <DropdownMenuItem onSelect={() => changeStatus(inv.id, "paid")}>
                            Mark paid
                          </DropdownMenuItem>
                        )}
                        {canManage && inv.status === "draft" && (
                          <DropdownMenuItem onSelect={() => changeStatus(inv.id, "sent")}>
                            Mark sent
                          </DropdownMenuItem>
                        )}
                        {canManage && inv.status === "sent" && (
                          <DropdownMenuItem onSelect={() => changeStatus(inv.id, "overdue")}>
                            Mark overdue
                          </DropdownMenuItem>
                        )}
                        {canDelete && inv.status !== "void" && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem danger onSelect={() => changeStatus(inv.id, "void")}>
                              Void
                            </DropdownMenuItem>
                          </>
                        )}
                        {canDelete && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem danger onSelect={() => setDeleting(inv)}>
                              <Trash2 className="h-4 w-4" aria-hidden="true" />
                              Delete
                            </DropdownMenuItem>
                          </>
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

      <Dialog open={Boolean(viewing)} onOpenChange={(open) => !open && setViewing(null)}>
        <DialogContent
          title={viewing ? `Invoice ${viewing.number}` : "Invoice"}
          description={
            viewing
              ? `${titleCase(viewing.status)} · issued ${formatDate(viewing.issued_at)} · due ${formatDate(viewing.due_at)}`
              : undefined
          }
          wide
        >
          {viewing && (
            <div className="space-y-4">
              {viewing.payment_url && (
                <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)] p-3">
                  <p className="text-xs font-medium">Online payment link</p>
                  <p className="truncate text-sm text-[var(--muted-foreground)]">
                    {viewing.payment_url}
                  </p>
                  <div className="mt-2 flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(viewing.payment_url ?? "");
                          toast.success("Payment link copied");
                        } catch {
                          window.prompt("Copy this payment link", viewing.payment_url ?? "");
                        }
                      }}
                    >
                      Copy
                    </Button>
                    <a
                      href={viewing.payment_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex h-8 items-center rounded-md px-3 text-xs font-medium text-[var(--brand-text)] underline underline-offset-2"
                    >
                      Open
                    </a>
                  </div>
                </div>
              )}
              {payError && (
                <p role="alert" className="text-sm text-[var(--destructive)]">
                  {payError}
                </p>
              )}
              <div className="hidden print:block">
                <p className="text-lg font-semibold">Invoice {viewing.number}</p>
                <p className="text-sm">
                  Issued {formatDate(viewing.issued_at)} · Due {formatDate(viewing.due_at)}
                </p>
              </div>
              <Table caption="Invoice lines" className="rounded-lg">
                <THead>
                  <TR>
                    <TH>Description</TH>
                    <TH numeric>Qty</TH>
                    <TH numeric>Unit price</TH>
                    <TH numeric>Total</TH>
                  </TR>
                </THead>
                <TBody>
                  {viewing.lines.map((line, index) => (
                    <TR key={index}>
                      <TD>{line.description ?? "—"}</TD>
                      <TD numeric>{line.quantity ?? "—"}</TD>
                      <TD numeric>{money(line.unit_price as string, viewing.currency)}</TD>
                      <TD numeric>{money(line.total as string, viewing.currency)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <dt className="text-[var(--muted-foreground)]">Subtotal</dt>
                  <dd>{money(viewing.subtotal, viewing.currency)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-[var(--muted-foreground)]">
                    Tax ({(Number.parseFloat(viewing.tax_rate || "0") * 100).toFixed(1)}%)
                  </dt>
                  <dd>{money(viewing.tax_amount, viewing.currency)}</dd>
                </div>
                <div className="flex justify-between border-t border-[var(--border)] pt-1 text-base font-semibold">
                  <dt>Total</dt>
                  <dd>{money(viewing.total, viewing.currency)}</dd>
                </div>
              </dl>
            </div>
          )}
          <DialogFooter>
            {viewing &&
              canManage &&
              !viewing.payment_url &&
              !["paid", "void"].includes(viewing.status) && (
                <Button variant="secondary" onClick={createPaymentLink} loading={payBusy}>
                  <CreditCard className="h-4 w-4" aria-hidden="true" />
                  Payment link
                </Button>
              )}
            {viewing && (
              <Button variant="secondary" onClick={() => window.print()}>
                <Printer className="h-4 w-4" aria-hidden="true" />
                Print
              </Button>
            )}
            <Button variant="secondary" onClick={() => setViewing(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={fromOrderOpen} onOpenChange={setFromOrderOpen}>
        <DialogContent
          title="Invoice from order"
          description="Pick a completed service order to invoice. Net 14 days."
        >
          <form onSubmit={createFromOrder} className="space-y-4">
            {fromOrderError && (
              <div role="alert" className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]">
                {fromOrderError}
              </div>
            )}
            <Field label="Completed order" htmlFor="io-order" required>
              <Select
                id="io-order"
                value={orderId}
                onChange={(e) => setOrderId(e.target.value)}
                required
              >
                <option value="">— select an order —</option>
                {(completedOrders.data?.items ?? []).map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.number} — {o.vehicle_plate ?? "?"} ({money(o.total, currency)})
                  </option>
                ))}
              </Select>
            </Field>
            {completedOrders.data && completedOrders.data.items.length === 0 && (
              <p className="text-sm text-[var(--muted-foreground)]">
                No completed orders are waiting to be invoiced.
              </p>
            )}
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setFromOrderOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={fromOrderBusy} disabled={!orderId}>
                Create invoice
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent
          title={`Delete ${deleting?.number ?? "invoice"}?`}
          description="This permanently removes the invoice. Voiding keeps the record instead."
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
