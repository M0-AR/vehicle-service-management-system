"use client";

import { useState } from "react";
import { MapPin, Pencil, Plus, Star, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/fields";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Location } from "@/lib/types";

interface FormState {
  name: string;
  address: string;
  phone: string;
}

const EMPTY_FORM: FormState = { name: "", address: "", phone: "" };

export function LocationsPanel({ canManage }: { canManage: boolean }) {
  const { data, error, isLoading, mutate } = useApi<Location[]>("/locations");

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Location | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Location | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setOpen(true);
  }

  function openEdit(location: Location) {
    setEditing(location);
    setForm({
      name: location.name,
      address: location.address ?? "",
      phone: location.phone ?? "",
    });
    setFormError(null);
    setOpen(true);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const body = {
        name: form.name.trim(),
        address: form.address.trim() || null,
        phone: form.phone.trim() || null,
      };
      if (editing) {
        await api(`/locations/${editing.id}`, { method: "PATCH", body });
        toast.success("Location updated");
      } else {
        await api("/locations", { body });
        toast.success("Location added");
      }
      setOpen(false);
      mutate();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function makeDefault(location: Location) {
    setBusyId(location.id);
    try {
      await api(`/locations/${location.id}`, { method: "PATCH", body: { is_default: true } });
      toast.success(`${location.name} is now the default location`);
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function remove() {
    if (!deleting) return;
    setBusyId(deleting.id);
    try {
      await api(`/locations/${deleting.id}`, { method: "DELETE" });
      toast.success("Location deleted");
      setDeleting(null);
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <MapPin className="h-4 w-4" aria-hidden="true" />
            Locations
          </CardTitle>
          <CardDescription>
            Branches of your business. New service orders default to the default location;
            customers and vehicles are shared across all branches.
          </CardDescription>
        </div>
        {canManage && (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add location
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {error && <ErrorState message="Could not load locations" retry={() => mutate()} />}
        {isLoading && !data && <LoadingBlock />}
        {data && data.length === 0 && (
          <EmptyState
            title="No locations yet"
            description="A default location is created automatically with every workspace."
          />
        )}
        {data && data.length > 0 && (
          <Table caption="Business locations">
            <THead>
              <TR>
                <TH>Name</TH>
                <TH className="hidden sm:table-cell">Address</TH>
                <TH className="hidden sm:table-cell">Phone</TH>
                {canManage && <TH className="text-right">Actions</TH>}
              </TR>
            </THead>
            <TBody>
              {data.map((location) => (
                <TR key={location.id}>
                  <TD>
                    <span className="font-medium">{location.name}</span>
                    {location.is_default && (
                      <Badge tone="brand" className="ml-2">
                        Default
                      </Badge>
                    )}
                  </TD>
                  <TD className="hidden text-[var(--muted-foreground)] sm:table-cell">
                    {location.address ?? "—"}
                  </TD>
                  <TD className="hidden text-[var(--muted-foreground)] sm:table-cell">
                    {location.phone ?? "—"}
                  </TD>
                  {canManage && (
                    <TD className="text-right">
                      <div className="flex justify-end gap-1">
                        {!location.is_default && (
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Make ${location.name} the default location`}
                            title="Make default"
                            loading={busyId === location.id}
                            onClick={() => makeDefault(location)}
                          >
                            <Star className="h-4 w-4" aria-hidden="true" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Edit ${location.name}`}
                          onClick={() => openEdit(location)}
                        >
                          <Pencil className="h-4 w-4" aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Delete ${location.name}`}
                          onClick={() => setDeleting(location)}
                        >
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                        </Button>
                      </div>
                    </TD>
                  )}
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title={editing ? "Edit location" : "Add location"}
          description="Name and contact details for this branch."
        >
          <form onSubmit={save} className="space-y-4">
            {formError && (
              <div role="alert" className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]">
                {formError}
              </div>
            )}
            <Field label="Name" htmlFor="loc-name" required>
              <Input
                id="loc-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                maxLength={120}
              />
            </Field>
            <Field label="Address" htmlFor="loc-address">
              <Input
                id="loc-address"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                maxLength={255}
              />
            </Field>
            <Field label="Phone" htmlFor="loc-phone">
              <Input
                id="loc-phone"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                maxLength={40}
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                {editing ? "Save changes" : "Add location"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={deleting !== null} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent
          title="Delete location"
          description={
            deleting
              ? `Delete ${deleting.name}? Locations with service orders cannot be deleted.`
              : undefined
          }
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              loading={busyId === deleting?.id}
              onClick={remove}
            >
              Delete location
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
