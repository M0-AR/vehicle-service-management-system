"use client";

// Digital vehicle inspection (DVI) panel for a service order. Photos are
// served by an authenticated endpoint, so thumbnails are fetched as blobs.

import { useEffect, useState } from "react";
import { Camera, Check, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input, Select, Textarea } from "@/components/ui/fields";
import { LoadingBlock } from "@/components/ui/feedback";
import { api, apiUpload, errorMessage, getToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { formatDate } from "@/lib/format";
import type { Inspection, InspectionItem, InspectionItemStatus } from "@/lib/types";

const STATUS_TONES: Record<InspectionItemStatus, "success" | "warning" | "danger" | "neutral"> = {
  ok: "success",
  attention: "warning",
  critical: "danger",
  na: "neutral",
};

const STATUS_LABELS: Record<InspectionItemStatus, string> = {
  ok: "OK",
  attention: "Attention",
  critical: "Critical",
  na: "N/A",
};

function PhotoThumb({ path, alt }: { path: string; alt: string }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    (async () => {
      try {
        const token = getToken();
        const res = await fetch(`/api/v1/inspections/photos/${path}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          credentials: "include",
        });
        if (!res.ok) return;
        const blob = await res.blob();
        if (cancelled) return;
        revoked = URL.createObjectURL(blob);
        setSrc(revoked);
      } catch {
        /* thumbnail stays empty */
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [path]);

  if (!src) {
    return <div className="h-16 w-16 animate-pulse rounded-md bg-[var(--muted)]" aria-hidden="true" />;
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} className="h-16 w-16 rounded-md border border-[var(--border)] object-cover" />
  );
}

export function InspectionPanel({
  orderId,
  canEdit,
  featureEnabled,
}: {
  orderId: string;
  canEdit: boolean;
  featureEnabled: boolean;
}) {
  const { data, error, isLoading, mutate } = useApi<Inspection | null>(
    featureEnabled ? `/inspections/by-order/${orderId}` : null,
  );
  const [busy, setBusy] = useState(false);
  const [label, setLabel] = useState("");
  const [status, setStatus] = useState<InspectionItemStatus>("ok");
  const [note, setNote] = useState("");
  const [adding, setAdding] = useState(false);
  const [uploadingId, setUploadingId] = useState<string | null>(null);

  if (!featureEnabled) return null;

  async function createInspection() {
    setBusy(true);
    try {
      await api(`/inspections/by-order/${orderId}`, { body: {} });
      toast.success("Inspection started");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function addItem(event: React.FormEvent) {
    event.preventDefault();
    if (!data) return;
    setAdding(true);
    try {
      await api(`/inspections/${data.id}/items`, {
        body: { label: label.trim(), status, note: note.trim() || null },
      });
      setLabel("");
      setNote("");
      setStatus("ok");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setAdding(false);
    }
  }

  async function updateItem(item: InspectionItem, patch: Record<string, unknown>) {
    if (!data) return;
    try {
      await api(`/inspections/${data.id}/items/${item.id}`, { method: "PATCH", body: patch });
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function removeItem(item: InspectionItem) {
    if (!data) return;
    try {
      await api(`/inspections/${data.id}/items/${item.id}`, { method: "DELETE" });
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function uploadPhoto(item: InspectionItem, file: File | null) {
    if (!data || !file) return;
    setUploadingId(item.id);
    try {
      await apiUpload(`/inspections/${data.id}/items/${item.id}/photos`, file);
      toast.success("Photo added");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setUploadingId(null);
    }
  }

  async function completeInspection() {
    if (!data) return;
    setBusy(true);
    try {
      await api(`/inspections/${data.id}`, { method: "PATCH", body: { status: "completed" } });
      toast.success("Inspection completed");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Inspection</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-[var(--destructive)]">
            Could not load the inspection. {errorMessage(error)}
          </p>
        </CardContent>
      </Card>
    );
  }
  if (isLoading && data === undefined) return <LoadingBlock label="Loading inspection" />;

  if (!data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Inspection</CardTitle>
          <CardDescription>
            Record condition with photos and share it on the customer status page.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={createInspection} loading={busy} disabled={!canEdit}>
            <Camera className="h-4 w-4" aria-hidden="true" />
            Start inspection
          </Button>
        </CardContent>
      </Card>
    );
  }

  const locked = data.status === "completed";

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle>Inspection</CardTitle>
            <CardDescription>
              {locked
                ? `Completed ${data.completed_at ? formatDate(data.completed_at) : ""}`
                : "Add the items you checked and attach photos."}
            </CardDescription>
          </div>
          {locked ? (
            <Badge tone="success">Completed</Badge>
          ) : (
            canEdit && (
              <Button variant="secondary" onClick={completeInspection} loading={busy}>
                <Check className="h-4 w-4" aria-hidden="true" />
                Complete
              </Button>
            )
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {data.items.length === 0 && (
          <p className="text-sm text-[var(--muted-foreground)]">No inspection items yet.</p>
        )}

        <ul className="divide-y divide-[var(--border)]">
          {data.items.map((item) => (
            <li key={item.id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-start">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{item.label}</span>
                  {locked ? (
                    <Badge tone={STATUS_TONES[item.status]}>
                      {STATUS_LABELS[item.status] ?? item.status}
                    </Badge>
                  ) : (
                    <Select
                      aria-label={`Status for ${item.label}`}
                      className="h-8 w-auto text-xs"
                      value={item.status}
                      onChange={(e) =>
                        updateItem(item, { status: e.target.value as InspectionItemStatus })
                      }
                    >
                      {Object.entries(STATUS_LABELS).map(([value, text]) => (
                        <option key={value} value={value}>
                          {text}
                        </option>
                      ))}
                    </Select>
                  )}
                </div>
                {item.note && (
                  <p className="mt-1 text-sm text-[var(--muted-foreground)]">{item.note}</p>
                )}
                {item.photos.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {item.photos.map((photo) => (
                      <PhotoThumb key={photo.path} path={photo.path} alt={item.label} />
                    ))}
                  </div>
                )}
              </div>
              {!locked && canEdit && (
                <div className="flex shrink-0 items-center gap-1">
                  <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--card)] px-2.5 py-1.5 text-xs font-medium hover:bg-[var(--muted)] focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--ring)]">
                    <Camera className="h-3.5 w-3.5" aria-hidden="true" />
                    {uploadingId === item.id ? "Uploading…" : "Photo"}
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      className="sr-only"
                      onChange={(e) => {
                        uploadPhoto(item, e.target.files?.[0] ?? null);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove ${item.label}`}
                    onClick={() => removeItem(item)}
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>

        {!locked && canEdit && (
          <form onSubmit={addItem} className="grid items-end gap-3 sm:grid-cols-[1fr_10rem_auto]">
            <Field label="Item" htmlFor="dvi-label">
              <Input
                id="dvi-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Brake pads"
                required
              />
            </Field>
            <Field label="Condition" htmlFor="dvi-status">
              <Select
                id="dvi-status"
                value={status}
                onChange={(e) => setStatus(e.target.value as InspectionItemStatus)}
              >
                {Object.entries(STATUS_LABELS).map(([value, text]) => (
                  <option key={value} value={value}>
                    {text}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Note" htmlFor="dvi-note" className="sm:col-span-2">
              <Textarea
                id="dvi-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Optional detail for the customer"
              />
            </Field>
            <Button type="submit" loading={adding}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
