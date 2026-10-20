"use client";

import { useState } from "react";
import {
  Download,
  ExternalLink,
  Plus,
  Search,
  Trash2,
  Truck,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader, SearchInput } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/fields";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, apiUpload, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBranding } from "@/lib/branding";
import { money } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import type {
  CatalogImportResult,
  SupplierConnection,
  SupplierOffer,
} from "@/lib/types";

const EMPTY_FORM = { name: "", provider: "stub", portal_url: "" };

export default function SuppliersPage() {
  const { user, hasFeature } = useAuth();
  const { currency } = useBranding();
  const enabled = hasFeature("suppliers");
  const canManage = ["owner", "admin"].includes(user?.role ?? "");

  const connections = useApi<SupplierConnection[]>(
    enabled ? "/suppliers" : null,
  );

  const [q, setQ] = useState("");
  const debouncedQ = useDebounced(q);
  const needle = debouncedQ.trim();
  const searchParams = new URLSearchParams({ q: needle, limit: "25" });
  const offers = useApi<SupplierOffer[]>(
    enabled && needle.length >= 2
      ? `/suppliers/search?${searchParams.toString()}`
      : null,
  );

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [deleting, setDeleting] = useState<SupplierConnection | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [importingCatalog, setImportingCatalog] = useState<string | null>(null);
  const [importingOffer, setImportingOffer] = useState<string | null>(null);

  function openCreate() {
    setForm(EMPTY_FORM);
    setFormError(null);
    setOpen(true);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await api<SupplierConnection>("/suppliers", {
        method: "POST",
        body: {
          name: form.name,
          provider: form.provider,
          portal_url: form.portal_url || null,
        },
      });
      toast.success("Supplier added");
      setOpen(false);
      connections.mutate();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function removeSupplier() {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api<{ ok: boolean }>(`/suppliers/${deleting.id}`, {
        method: "DELETE",
      });
      toast.success("Supplier removed");
      setDeleting(null);
      connections.mutate();
      offers.mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setDeleteBusy(false);
    }
  }

  async function uploadCatalog(
    connection: SupplierConnection,
    file: File | undefined,
  ) {
    if (!file) return;
    setImportingCatalog(connection.id);
    try {
      const result = await apiUpload<CatalogImportResult>(
        `/suppliers/${connection.id}/catalog`,
        file,
      );
      const extra = result.skipped ? `, ${result.skipped} skipped` : "";
      toast.success(
        `Catalog imported: ${result.imported} new, ${result.updated} updated${extra}`,
      );
      connections.mutate();
      offers.mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setImportingCatalog(null);
    }
  }

  async function importOffer(offer: SupplierOffer) {
    const key = `${offer.connection_id}:${offer.sku}`;
    setImportingOffer(key);
    try {
      const result = await api<{ part_id: string; created: boolean }>(
        "/suppliers/import",
        {
          method: "POST",
          body: { connection_id: offer.connection_id, sku: offer.sku },
        },
      );
      toast.success(
        result.created
          ? `${offer.sku} added to inventory`
          : `${offer.sku} updated in inventory`,
      );
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setImportingOffer(null);
    }
  }

  if (!enabled) {
    return (
      <div className="space-y-6">
        <PageHeader title="Suppliers" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Truck className="h-8 w-8 text-[var(--muted-foreground)]" aria-hidden="true" />
            <p className="text-sm font-medium">Suppliers are available on Pro and Enterprise.</p>
            <p className="max-w-sm text-sm text-[var(--muted-foreground)]">
              Search distributor catalogs, compare price and availability, and import
              parts straight into inventory.
            </p>
            <Button onClick={() => (window.location.href = "/app/settings")}>
              View plans
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Suppliers"
        description="Search distributor catalogs and import parts into inventory."
      >
        {canManage && (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" /> Add supplier
          </Button>
        )}
      </PageHeader>

      <Card>
        <CardContent className="space-y-4 pt-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold">Supplier connections</h2>
              <p className="text-xs text-[var(--muted-foreground)]">
                Stub suppliers ship with a demo catalog; CSV suppliers accept a price-list upload.
              </p>
            </div>
          </div>

          {connections.error ? (
            <ErrorState message={errorMessage(connections.error)} retry={connections.mutate} />
          ) : connections.isLoading ? (
            <TableSkeleton rows={3} cols={4} />
          ) : !connections.data?.length ? (
            <div className="rounded-lg border border-dashed border-[var(--border)] px-4 py-8 text-center">
              <p className="text-sm font-medium">No suppliers connected yet</p>
              <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                Add a supplier to start searching its catalog.
              </p>
            </div>
          ) : (
            <Table caption="Supplier connections">
              <THead>
                <TR>
                  <TH>Supplier</TH>
                  <TH>Provider</TH>
                  <TH className="text-right">Catalog</TH>
                  <TH className="text-right">Actions</TH>
                </TR>
              </THead>
              <TBody>
                {connections.data.map((connection) => (
                  <TR key={connection.id}>
                    <TD>
                      <div className="font-medium">{connection.name}</div>
                      {connection.portal_url && (
                        <a
                          href={connection.portal_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-[var(--brand-primary)] hover:underline"
                        >
                          Open portal
                          <ExternalLink className="h-3 w-3" aria-hidden="true" />
                        </a>
                      )}
                    </TD>
                    <TD>
                      <Badge tone={connection.provider === "csv" ? "success" : "info"}>
                        {connection.provider === "csv" ? "CSV catalog" : "Demo catalog"}
                      </Badge>
                    </TD>
                    <TD className="text-right tabular-nums">
                      {connection.provider === "csv"
                        ? connection.catalog_size.toLocaleString()
                        : "Built-in"}
                    </TD>
                    <TD className="text-right">
                      <div className="flex flex-wrap items-center justify-end gap-1">
                        {canManage && connection.provider === "csv" && (
                          <>
                            <input
                              id={`catalog-${connection.id}`}
                              type="file"
                              accept=".csv,text/csv"
                              className="sr-only"
                              aria-hidden="true"
                              tabIndex={-1}
                              onChange={(event) => {
                                void uploadCatalog(connection, event.target.files?.[0]);
                                event.target.value = "";
                              }}
                            />
                            <Button
                              variant="secondary"
                              size="sm"
                              loading={importingCatalog === connection.id}
                              onClick={() =>
                                document.getElementById(`catalog-${connection.id}`)?.click()
                              }
                            >
                              <Download className="h-4 w-4" aria-hidden="true" /> Import CSV
                            </Button>
                          </>
                        )}
                        {canManage && (
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Remove ${connection.name}`}
                            onClick={() => setDeleting(connection)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}

          {canManage && (
            <p className="text-xs text-[var(--muted-foreground)]">
              CSV header: <code>sku,description,brand,cost,price,stock</code> — only
              <code> sku</code> and <code>description</code> are required. Rows upsert on SKU.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-4 pt-5">
          <div>
            <h2 className="text-sm font-semibold">Search supplier catalogs</h2>
            <p className="text-xs text-[var(--muted-foreground)]">
              Look up a part number or description across every connection.
            </p>
          </div>
          <SearchInput
            value={q}
            onChange={setQ}
            placeholder="Part number or description"
            label="Search supplier catalogs"
          />

          {needle.length < 2 ? (
            <div className="flex items-center gap-2 rounded-lg border border-dashed border-[var(--border)] px-4 py-6 text-sm text-[var(--muted-foreground)]">
              <Search className="h-4 w-4" aria-hidden="true" />
              Type at least two characters to search.
            </div>
          ) : offers.error ? (
            <ErrorState message={errorMessage(offers.error)} retry={offers.mutate} />
          ) : offers.isLoading ? (
            <TableSkeleton rows={4} cols={6} />
          ) : !offers.data?.length ? (
            <EmptyState
              title="No matching offers"
              description="Try another part number or description, or import a newer CSV price list."
            />
          ) : (
            <Table caption="Supplier offers">
              <THead>
                <TR>
                  <TH>Supplier</TH>
                  <TH>Part</TH>
                  <TH className="text-right">Cost</TH>
                  <TH className="text-right">Price</TH>
                  <TH className="text-right">Stock</TH>
                  <TH className="text-right">Actions</TH>
                </TR>
              </THead>
              <TBody>
                {offers.data.map((offer) => {
                  const key = `${offer.connection_id}:${offer.sku}`;
                  return (
                    <TR key={key}>
                      <TD>
                        <div className="font-medium">{offer.supplier}</div>
                        {offer.portal_url && (
                          <a
                            href={offer.portal_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-[var(--brand-primary)] hover:underline"
                          >
                            Order on portal
                            <ExternalLink className="h-3 w-3" aria-hidden="true" />
                          </a>
                        )}
                      </TD>
                      <TD>
                        <div className="font-medium">{offer.description}</div>
                        <div className="text-xs text-[var(--muted-foreground)]">
                          {offer.sku}
                          {offer.brand ? ` · ${offer.brand}` : ""}
                        </div>
                      </TD>
                      <TD className="text-right tabular-nums">{money(offer.cost, currency)}</TD>
                      <TD className="text-right tabular-nums">{money(offer.price, currency)}</TD>
                      <TD className="text-right tabular-nums">{Number(offer.stock_qty)}</TD>
                      <TD className="text-right">
                        <Button
                          variant="secondary"
                          size="sm"
                          loading={importingOffer === key}
                          onClick={() => void importOffer(offer)}
                        >
                          Import
                        </Button>
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title="Add supplier"
          description="Connect a distributor catalog. Demo suppliers use a built-in catalog; CSV suppliers accept a price-list upload after saving."
        >
          <form onSubmit={save} className="space-y-4">
            <Field label="Name" htmlFor="supplier-name">
              <Input
                id="supplier-name"
                value={form.name}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, name: event.target.value }))
                }
                required
              />
            </Field>
            <Field label="Provider" htmlFor="supplier-provider">
              <Select
                id="supplier-provider"
                value={form.provider}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, provider: event.target.value }))
                }
              >
                <option value="stub">Demo catalog (built-in)</option>
                <option value="csv">CSV price list</option>
              </Select>
            </Field>
            <Field
              label="Portal URL"
              htmlFor="supplier-portal"
              hint="Optional — shown as the order link on offers"
            >
              <Input
                id="supplier-portal"
                type="url"
                placeholder="https://distributor.example/order"
                value={form.portal_url}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, portal_url: event.target.value }))
                }
              />
            </Field>
            {formError && (
              <p className="text-sm text-[var(--destructive)]" role="alert">
                {formError}
              </p>
            )}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                Add supplier
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={deleting !== null} onOpenChange={(value) => !value && setDeleting(null)}>
        <DialogContent
          title={`Remove ${deleting?.name ?? "supplier"}?`}
          description="The connection and its uploaded catalog are deleted. Parts already imported into inventory are kept."
        >
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button variant="destructive" loading={deleteBusy} onClick={() => void removeSupplier()}>
              Remove supplier
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
