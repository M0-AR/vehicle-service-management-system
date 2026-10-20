"use client";

// Settings panels — one component per tab. Role/feature gating happens in the
// page (tab visibility) and here (disabled controls) so the UI always mirrors
// what the API will actually allow.

import { useEffect, useState } from "react";
import { BellRing, Check, Copy, Download, Globe, KeyRound, MessageSquare, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/fields";
import { ErrorState, LoadingBlock, TableSkeleton } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, downloadCsv, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  currentDeviceEndpoint,
  pushSupported,
  removePushSubscription,
  subscribeCurrentDevice,
  type PushConfig,
  type PushSubscriptionRow,
} from "@/lib/push";
import { readableOn } from "@/lib/branding";
import { formatDate, formatDateTime, money, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type {
  ApiKey,
  ApiKeyCreated,
  BillingStatus,
  CheckoutResponse,
  Domain,
  NotificationRow,
  OperationsSettings,
  Page,
  Plan,
  User,
} from "@/lib/types";

const HEX = /^#[0-9a-fA-F]{6}$/;

async function copyText(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(`${what} copied`);
  } catch {
    toast.error("Could not copy to clipboard");
  }
}

interface BrandData {
  primary_color?: string;
  accent_color?: string;
  display_name?: string | null;
  logo_url?: string | null;
  support_email?: string | null;
}

interface BrandingResponse {
  brand: BrandData;
  white_label: boolean;
  currency: string;
  locale: string;
}

// --- branding & profile -------------------------------------------------------

export function BrandingPanel({ canEdit }: { canEdit: boolean }) {
  const { tenant } = useAuth();
  const { data, error, mutate } = useApi<BrandingResponse>("/settings/branding");

  const [initialized, setInitialized] = useState(false);
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [locale, setLocale] = useState("en");
  const [primary, setPrimary] = useState("#0f766e");
  const [accent, setAccent] = useState("#f59e0b");
  const [logoUrl, setLogoUrl] = useState("");
  const [supportEmail, setSupportEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (data && !initialized) {
      setName(tenant?.name ?? "");
      setDisplayName(data.brand.display_name ?? "");
      setCurrency(data.currency || "USD");
      setLocale(data.locale || "en");
      setPrimary(data.brand.primary_color ?? "#0f766e");
      setAccent(data.brand.accent_color ?? "#f59e0b");
      setLogoUrl(data.brand.logo_url ?? "");
      setSupportEmail(data.brand.support_email ?? "");
      setInitialized(true);
    }
  }, [data, initialized, tenant]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);

    if (!HEX.test(primary) || !HEX.test(accent)) {
      setFormError("Colors must be hex values like #0f766e.");
      return;
    }

    setBusy(true);
    try {
      if (name.trim() && name.trim() !== tenant?.name) {
        await api("/settings/profile", { method: "PATCH", body: { name: name.trim() } });
      }
      const body: Record<string, unknown> = {
        display_name: displayName.trim() || null,
        currency,
        locale,
      };
      if (data?.white_label) {
        body.primary_color = primary;
        body.accent_color = accent;
        body.logo_url = logoUrl.trim() || null;
        body.support_email = supportEmail.trim() || null;
      }
      await api("/settings/branding", { method: "PATCH", body });

      const root = document.documentElement;
      root.style.setProperty("--brand-primary", primary);
      root.style.setProperty("--brand-accent", accent);
      root.style.setProperty("--brand-primary-fg", readableOn(primary));
      toast.success("Branding saved");
      mutate();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorState message="Could not load branding" retry={() => mutate()} />;
  if (!data) return <LoadingBlock />;

  const locked = !data.white_label;

  return (
    <form onSubmit={save} className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Workspace profile</CardTitle>
          <CardDescription>Shown across the app and on documents.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Business name" htmlFor="set-name">
            <Input
              id="set-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!canEdit}
              maxLength={120}
              required
            />
          </Field>
          <Field label="Display name" htmlFor="set-display" hint="Optional name shown in the sidebar.">
            <Input
              id="set-display"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              disabled={!canEdit}
              maxLength={120}
              placeholder={name}
            />
          </Field>
          <Field label="Currency" htmlFor="set-currency">
            <Select id="set-currency" value={currency} onChange={(e) => setCurrency(e.target.value)} disabled={!canEdit}>
              <option value="USD">USD — US Dollar</option>
              <option value="EUR">EUR — Euro</option>
              <option value="GBP">GBP — British Pound</option>
              <option value="TRY">TRY — Turkish Lira</option>
              <option value="AED">AED — UAE Dirham</option>
            </Select>
          </Field>
          <Field label="Language" htmlFor="set-locale">
            <Select id="set-locale" value={locale} onChange={(e) => setLocale(e.target.value)} disabled={!canEdit}>
              <option value="en">English</option>
              <option value="de">Deutsch</option>
              <option value="fr">Français</option>
              <option value="es">Español</option>
              <option value="tr">Türkçe</option>
              <option value="ar">العربية</option>
            </Select>
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle>Brand colors & identity</CardTitle>
            {locked && <Badge tone="warning">Pro feature</Badge>}
          </div>
          <CardDescription>
            {locked
              ? "Custom colors, logo and support email are available on the Pro plan."
              : "These apply instantly to your workspace and customer-facing pages."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Primary color" htmlFor="set-primary">
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={HEX.test(primary) ? primary : "#0f766e"}
                onChange={(e) => setPrimary(e.target.value)}
                disabled={!canEdit || locked}
                aria-label="Pick primary color"
                className="h-9 w-12 cursor-pointer rounded-md border border-[var(--border)] bg-transparent p-1 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <Input
                id="set-primary"
                value={primary}
                onChange={(e) => setPrimary(e.target.value)}
                disabled={!canEdit || locked}
                pattern="^#[0-9a-fA-F]{6}$"
                placeholder="#0f766e"
              />
            </div>
          </Field>
          <Field label="Accent color" htmlFor="set-accent">
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={HEX.test(accent) ? accent : "#f59e0b"}
                onChange={(e) => setAccent(e.target.value)}
                disabled={!canEdit || locked}
                aria-label="Pick accent color"
                className="h-9 w-12 cursor-pointer rounded-md border border-[var(--border)] bg-transparent p-1 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <Input
                id="set-accent"
                value={accent}
                onChange={(e) => setAccent(e.target.value)}
                disabled={!canEdit || locked}
                pattern="^#[0-9a-fA-F]{6}$"
                placeholder="#f59e0b"
              />
            </div>
          </Field>
          <Field label="Logo URL" htmlFor="set-logo" hint="A square PNG or SVG works best.">
            <Input
              id="set-logo"
              type="url"
              value={logoUrl}
              onChange={(e) => setLogoUrl(e.target.value)}
              disabled={!canEdit || locked}
              placeholder="https://…/logo.png"
            />
          </Field>
          <Field label="Support email" htmlFor="set-support">
            <Input
              id="set-support"
              type="email"
              value={supportEmail}
              onChange={(e) => setSupportEmail(e.target.value)}
              disabled={!canEdit || locked}
              placeholder="support@your-garage.com"
            />
          </Field>
        </CardContent>
      </Card>

      {formError && (
        <div role="alert" className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]">
          {formError}
        </div>
      )}

      {canEdit ? (
        <div className="flex justify-end">
          <Button type="submit" loading={busy}>
            Save changes
          </Button>
        </div>
      ) : (
        <p className="text-sm text-[var(--muted-foreground)]">
          Ask an owner or admin to change workspace settings.
        </p>
      )}
    </form>
  );
}

// --- team ---------------------------------------------------------------------

const ROLE_OPTIONS = ["admin", "manager", "mechanic", "viewer"];

export function StaffPanel({ canManage }: { canManage: boolean }) {
  const { user: me } = useAuth();
  const { data, error, isLoading, mutate } = useApi<Page<User>>("/staff?page_size=100");

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteName, setInviteName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [invitePassword, setInvitePassword] = useState("");
  const [inviteRole, setInviteRole] = useState("mechanic");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<User | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);

  async function invite(event: React.FormEvent) {
    event.preventDefault();
    setInviteBusy(true);
    setInviteError(null);
    try {
      await api("/staff", {
        body: { name: inviteName, email: inviteEmail, password: invitePassword, role: inviteRole },
      });
      toast.success(`${inviteEmail} added to the team`);
      setInviteOpen(false);
      setInviteName("");
      setInviteEmail("");
      setInvitePassword("");
      setInviteRole("mechanic");
      mutate();
    } catch (err) {
      setInviteError(errorMessage(err));
    } finally {
      setInviteBusy(false);
    }
  }

  async function patch(user: User, body: Record<string, unknown>, message: string) {
    try {
      await api(`/staff/${user.id}`, { method: "PATCH", body });
      toast.success(message);
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function confirmRemove() {
    if (!removing) return;
    setRemoveBusy(true);
    try {
      await api(`/staff/${removing.id}`, { method: "DELETE" });
      toast.success("Team member removed");
      setRemoving(null);
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setRemoveBusy(false);
    }
  }

  if (error) return <ErrorState message="Could not load the team" retry={() => mutate()} />;
  if (isLoading && !data) return <TableSkeleton rows={4} cols={5} />;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--muted-foreground)]">
          Everyone who can sign in to this workspace.
        </p>
        {canManage && (
          <Button onClick={() => setInviteOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add member
          </Button>
        )}
      </div>

      {data && (
        <Table caption="Team members">
          <THead>
            <TR>
              <TH>Name</TH>
              <TH className="hidden sm:table-cell">Email</TH>
              <TH>Role</TH>
              <TH>Status</TH>
              <TH className="hidden md:table-cell">Last login</TH>
              <TH><span className="sr-only">Actions</span></TH>
            </TR>
          </THead>
          <TBody>
            {data.items.map((member) => {
              const isOwnerRow = member.role === "owner";
              const isSelf = member.id === me?.id;
              const roleLocked = !canManage || (isOwnerRow && me?.role !== "owner");
              return (
                <TR key={member.id}>
                  <TD className="font-medium">
                    {member.name}
                    {isSelf && <span className="ml-2 text-xs text-[var(--muted-foreground)]">(you)</span>}
                  </TD>
                  <TD className="hidden text-[var(--muted-foreground)] sm:table-cell">{member.email}</TD>
                  <TD>
                    {isOwnerRow ? (
                      <Badge tone="brand">Owner</Badge>
                    ) : (
                      <Select
                        value={member.role}
                        disabled={roleLocked}
                        aria-label={`Role for ${member.name}`}
                        onChange={(e) => patch(member, { role: e.target.value }, "Role updated")}
                        className="h-8 w-32 text-xs"
                      >
                        {ROLE_OPTIONS.map((r) => (
                          <option key={r} value={r}>
                            {titleCase(r)}
                          </option>
                        ))}
                      </Select>
                    )}
                  </TD>
                  <TD>
                    <Badge tone={member.is_active ? "success" : "neutral"}>
                      {member.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </TD>
                  <TD className="hidden text-[var(--muted-foreground)] md:table-cell">
                    {formatDateTime(member.last_login_at)}
                  </TD>
                  <TD className="w-44 text-right">
                    {canManage && !isSelf && !isOwnerRow && (
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            patch(
                              member,
                              { is_active: !member.is_active },
                              member.is_active ? "Deactivated" : "Reactivated",
                            )
                          }
                        >
                          {member.is_active ? "Deactivate" : "Activate"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Remove ${member.name}`}
                          onClick={() => setRemoving(member)}
                        >
                          <Trash2 className="h-4 w-4 text-[var(--destructive)]" aria-hidden="true" />
                        </Button>
                      </div>
                    )}
                  </TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      )}

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent title="Add team member" description="They can sign in immediately with this password.">
          <form onSubmit={invite} className="space-y-4">
            {inviteError && (
              <div role="alert" className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]">
                {inviteError}
              </div>
            )}
            <Field label="Name" htmlFor="staff-name" required>
              <Input id="staff-name" value={inviteName} onChange={(e) => setInviteName(e.target.value)} required maxLength={120} />
            </Field>
            <Field label="Email" htmlFor="staff-email" required>
              <Input id="staff-email" type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} required />
            </Field>
            <Field label="Temporary password" htmlFor="staff-pass" hint="At least 8 characters." required>
              <Input
                id="staff-pass"
                type="password"
                value={invitePassword}
                onChange={(e) => setInvitePassword(e.target.value)}
                required
                minLength={8}
              />
            </Field>
            <Field label="Role" htmlFor="staff-role">
              <Select id="staff-role" value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
                {ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {titleCase(r)}
                  </option>
                ))}
              </Select>
            </Field>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setInviteOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={inviteBusy}>
                Add member
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(removing)} onOpenChange={(open) => !open && setRemoving(null)}>
        <DialogContent
          title={`Remove ${removing?.name ?? "team member"}?`}
          description="They lose access immediately. Their audit history stays."
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setRemoving(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmRemove} loading={removeBusy}>
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// --- API keys -----------------------------------------------------------------

export function ApiKeysPanel({ canManage }: { canManage: boolean }) {
  const { data, error, isLoading, mutate } = useApi<ApiKey[]>("/settings/api-keys");

  const [createOpen, setCreateOpen] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [revoking, setRevoking] = useState<ApiKey | null>(null);
  const [revokeBusy, setRevokeBusy] = useState(false);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setCreateBusy(true);
    setCreateError(null);
    try {
      const result = await api<ApiKeyCreated>("/settings/api-keys", { body: { name: keyName } });
      setCreateOpen(false);
      setKeyName("");
      setCreated(result);
      mutate();
    } catch (err) {
      setCreateError(errorMessage(err));
    } finally {
      setCreateBusy(false);
    }
  }

  async function confirmRevoke() {
    if (!revoking) return;
    setRevokeBusy(true);
    try {
      await api(`/settings/api-keys/${revoking.id}`, { method: "DELETE" });
      toast.success(`Revoked ${revoking.name}`);
      setRevoking(null);
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setRevokeBusy(false);
    }
  }

  if (error) return <ErrorState message="Could not load API keys" retry={() => mutate()} />;
  if (isLoading && !data) return <TableSkeleton rows={3} cols={4} />;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4" aria-hidden="true" />
            API keys
          </CardTitle>
          <CardDescription>
            Use keys with the REST API: send them as <code className="rounded bg-[var(--muted)] px-1">X-Api-Key</code>{" "}
            together with your workspace header.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {canManage && (
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" aria-hidden="true" />
                Create key
              </Button>
            </div>
          )}
          {data && data.length === 0 && (
            <p className="py-6 text-center text-sm text-[var(--muted-foreground)]">
              No API keys yet.
            </p>
          )}
          {data && data.length > 0 && (
            <Table caption="API keys">
              <THead>
                <TR>
                  <TH>Name</TH>
                  <TH className="hidden sm:table-cell">Created</TH>
                  <TH className="hidden sm:table-cell">Last used</TH>
                  <TH><span className="sr-only">Actions</span></TH>
                </TR>
              </THead>
              <TBody>
                {data.map((key) => (
                  <TR key={key.id}>
                    <TD className="font-medium">{key.name}</TD>
                    <TD className="hidden text-[var(--muted-foreground)] sm:table-cell">
                      {formatDate(key.created_at)}
                    </TD>
                    <TD className="hidden text-[var(--muted-foreground)] sm:table-cell">
                      {key.last_used_at ? formatDateTime(key.last_used_at) : "Never"}
                    </TD>
                    <TD className="w-24 text-right">
                      {canManage && (
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Revoke ${key.name}`}
                          onClick={() => setRevoking(key)}
                        >
                          <Trash2 className="h-4 w-4 text-[var(--destructive)]" aria-hidden="true" />
                        </Button>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent title="Create API key" description="Name it after the system that will use it.">
          <form onSubmit={create} className="space-y-4">
            {createError && (
              <div role="alert" className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]">
                {createError}
              </div>
            )}
            <Field label="Key name" htmlFor="key-name" required>
              <Input
                id="key-name"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                required
                maxLength={120}
                placeholder="e.g. Workshop tablet"
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={createBusy}>
                Create key
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(created)} onOpenChange={(open) => !open && setCreated(null)}>
        <DialogContent
          title="Copy your API key now"
          description="For security, this is the only time the full key is shown."
        >
          {created && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm">
                  {created.key}
                </code>
                <Button
                  variant="secondary"
                  size="icon"
                  aria-label="Copy API key"
                  onClick={() => copyText(created.key, "API key")}
                >
                  <Copy className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
              <p className="text-sm text-[color-mix(in_oklab,var(--warning)_60%,var(--foreground))]">{created.warning}</p>
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setCreated(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(revoking)} onOpenChange={(open) => !open && setRevoking(null)}>
        <DialogContent
          title={`Revoke ${revoking?.name ?? "key"}?`}
          description="Any system using this key will stop working immediately."
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setRevoking(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmRevoke} loading={revokeBusy}>
              Revoke key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// --- custom domains -----------------------------------------------------------

export function DomainsPanel() {
  const { data, error, isLoading, mutate } = useApi<Domain[]>("/settings/domains");

  const [addOpen, setAddOpen] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  const [addBusy, setAddBusy] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Domain | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [verifying, setVerifying] = useState<string | null>(null);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setAddBusy(true);
    setAddError(null);
    try {
      await api<Domain>("/settings/domains", { body: { domain: newDomain.trim().toLowerCase() } });
      toast.success("Domain added — publish the TXT record to verify it");
      setAddOpen(false);
      setNewDomain("");
      mutate();
    } catch (err) {
      setAddError(errorMessage(err));
    } finally {
      setAddBusy(false);
    }
  }

  async function verify(domain: Domain) {
    setVerifying(domain.domain);
    try {
      const result = await api<Domain>(`/settings/domains/${encodeURIComponent(domain.domain)}/verify`, {
        method: "POST",
      });
      if (result.status === "verified") {
        toast.success(`${domain.domain} verified — it is live now`);
      } else {
        toast.error("Verification failed — check the TXT record and allow a few minutes for DNS.");
      }
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setVerifying(null);
    }
  }

  async function confirmRemove() {
    if (!removing) return;
    setRemoveBusy(true);
    try {
      await api(`/settings/domains/${encodeURIComponent(removing.domain)}`, { method: "DELETE" });
      toast.success("Domain removed");
      setRemoving(null);
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setRemoveBusy(false);
    }
  }

  if (error) return <ErrorState message="Could not load domains" retry={() => mutate()} />;
  if (isLoading && !data) return <LoadingBlock />;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Globe className="h-4 w-4" aria-hidden="true" />
                Custom domains
              </CardTitle>
              <CardDescription>
                Serve this workspace on your own domain, with automatic HTTPS.
              </CardDescription>
            </div>
            <Button size="sm" onClick={() => setAddOpen(true)}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add domain
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {data && data.length === 0 && (
            <p className="py-6 text-center text-sm text-[var(--muted-foreground)]">
              No custom domains yet.
            </p>
          )}
          {data?.map((domain) => (
            <div
              key={domain.domain}
              className="rounded-xl border border-[var(--border)] p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="font-medium">{domain.domain}</span>
                  <Badge tone={domain.status === "verified" ? "success" : "warning"}>
                    {titleCase(domain.status)}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  {domain.status !== "verified" && (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={verifying === domain.domain}
                      onClick={() => verify(domain)}
                    >
                      <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                      Check verification
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove ${domain.domain}`}
                    onClick={() => setRemoving(domain)}
                  >
                    <Trash2 className="h-4 w-4 text-[var(--destructive)]" aria-hidden="true" />
                  </Button>
                </div>
              </div>
              {domain.status !== "verified" && (
                <div className="mt-3 space-y-2 rounded-lg bg-[var(--muted)] p-3 text-sm">
                  <p className="text-[var(--muted-foreground)]">
                    Add this DNS record at your domain registrar, then check verification:
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs">
                      TXT&nbsp;&nbsp;_vsms-verify.{domain.domain}&nbsp;&nbsp;→&nbsp;&nbsp;{domain.txt_record}
                    </span>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => copyText(domain.txt_record, "TXT value")}
                    >
                      <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                      Copy value
                    </Button>
                  </div>
                </div>
              )}
              {domain.verified_at && (
                <p className="mt-2 text-xs text-[var(--muted-foreground)]">
                  Verified {formatDate(domain.verified_at)}
                </p>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent
          title="Add custom domain"
          description="Enter the bare hostname — no https:// or trailing slash."
        >
          <form onSubmit={add} className="space-y-4">
            {addError && (
              <div role="alert" className="rounded-lg border border-[color-mix(in_oklab,var(--destructive)_35%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] text-[var(--destructive)]">
                {addError}
              </div>
            )}
            <Field label="Domain" htmlFor="dom-name" required>
              <Input
                id="dom-name"
                value={newDomain}
                onChange={(e) => setNewDomain(e.target.value)}
                required
                placeholder="service.my-garage.com"
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setAddOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={addBusy}>
                Add domain
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(removing)} onOpenChange={(open) => !open && setRemoving(null)}>
        <DialogContent
          title={`Remove ${removing?.domain ?? "domain"}?`}
          description="The domain stops serving this workspace immediately."
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setRemoving(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmRemove} loading={removeBusy}>
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const FEATURE_LABELS: Record<string, string> = {
  audit_log: "Audit log",
  api_access: "API access",
  white_label: "White label",
  custom_domain: "Custom domains",
  byok: "BYOK (your own keys)",
  online_payments: "Online invoice payments",
  sms_notifications: "SMS notifications",
  dvi: "Digital inspections",
  online_booking: "Online booking",
  review_requests: "Review requests",
};

// --- billing ------------------------------------------------------------------

export function BillingPanel({ highlight }: { highlight?: string }) {
  const { user, reloadMe } = useAuth();
  const canCheckout =
    Boolean(user && ["owner", "admin"].includes(user.role));
  const billing = useApi<BillingStatus>("/settings/billing");
  const plans = useApi<Plan[]>("/settings/plans");
  const [busyPlan, setBusyPlan] = useState<string | null>(null);

  async function checkout(plan: Plan) {
    setBusyPlan(plan.id);
    try {
      const result = await api<CheckoutResponse>("/settings/billing/checkout", {
        body: { plan: plan.id },
      });
      if (result.url) {
        window.location.href = result.url;
        return;
      }
      toast.success(result.message || `${plan.name} activated`);
      await reloadMe();
      billing.mutate();
      plans.mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusyPlan(null);
    }
  }

  if (billing.error || plans.error) {
    return <ErrorState message="Could not load billing" retry={() => { billing.mutate(); plans.mutate(); }} />;
  }
  if (!billing.data || !plans.data) return <LoadingBlock />;

  const status = billing.data;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Subscription</CardTitle>
          <CardDescription>
            Plan <strong>{titleCase(status.plan)}</strong> · status {status.status}
            {status.current_period_end && <> · renews {formatDate(status.current_period_end)}</>}
            {" "}· billed via {titleCase(status.provider)} ({status.currency})
          </CardDescription>
        </CardHeader>
        {!status.checkout_available && (
          <CardContent>
            <p className="rounded-lg bg-[var(--muted)] px-3 py-2 text-sm text-[var(--muted-foreground)]">
              This environment has no payment provider configured, so plan changes apply
              instantly and no card is charged.
            </p>
          </CardContent>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {plans.data.map((plan) => {
          const isCurrent = plan.id === status.plan;
          const isHighlighted = highlight === plan.id && !isCurrent;
          const users = plan.limits?.users;
          return (
            <Card
              key={plan.id}
              className={isHighlighted ? "border-[var(--brand-primary)] ring-2 ring-[var(--brand-primary)]/20" : undefined}
            >
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>{plan.name}</CardTitle>
                  {isCurrent ? (
                    <Badge tone="success">Current plan</Badge>
                  ) : isHighlighted ? (
                    <Badge tone="brand">Recommended</Badge>
                  ) : null}
                </div>
                <CardDescription>
                  <span className="text-2xl font-semibold text-[var(--foreground)]">
                    {plan.price_monthly_usd === 0 ? "Free" : `${money(plan.price_monthly_usd, "USD")}/mo`}
                  </span>
                  {users !== undefined && (
                    <span className="ml-2">· {users < 0 ? "unlimited users" : `up to ${users} users`}</span>
                  )}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <ul className="space-y-2 text-sm">
                  {Object.entries(plan.features)
                    .filter(([, enabled]) => enabled)
                    .map(([feature]) => (
                      <li key={feature} className="flex items-center gap-2">
                        <Check className="h-4 w-4 text-[var(--success)]" aria-hidden="true" />
                        {FEATURE_LABELS[feature] ?? titleCase(feature)}
                      </li>
                    ))}
                </ul>
                {isCurrent ? (
                  <Button variant="secondary" disabled className="w-full">
                    Current plan
                  </Button>
                ) : plan.id === "free" ? (
                  <Button variant="secondary" disabled className="w-full">
                    Downgrade in billing portal
                  </Button>
                ) : (
                  <Button
                    className="w-full"
                    disabled={!canCheckout}
                    loading={busyPlan === plan.id}
                    onClick={() => checkout(plan)}
                  >
                    {canCheckout ? `Upgrade to ${plan.name}` : "Ask an owner to upgrade"}
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

// --- exports ------------------------------------------------------------------

const EXPORT_RESOURCES = [
  { id: "vehicles", label: "Vehicles" },
  { id: "customers", label: "Customers" },
  { id: "orders", label: "Orders" },
  { id: "invoices", label: "Invoices" },
];

export function ExportsPanel() {
  const [busy, setBusy] = useState<string | null>(null);

  async function run(resource: string) {
    setBusy(resource);
    try {
      await downloadCsv(resource);
      toast.success(`${resource}.csv downloaded`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Export your data</CardTitle>
        <CardDescription>
          CSV files with the full current contents of each table. Your data is always yours —
          download it any time.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2">
        {EXPORT_RESOURCES.map((resource) => (
          <Button
            key={resource.id}
            variant="secondary"
            loading={busy === resource.id}
            onClick={() => run(resource.id)}
            className="justify-start"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            {resource.label} CSV
          </Button>
        ))}
      </CardContent>
    </Card>
  );
}

// --- operations (booking, reviews, SMS) --------------------------------------

const DAYS: Array<[string, string]> = [
  ["mon", "Monday"],
  ["tue", "Tuesday"],
  ["wed", "Wednesday"],
  ["thu", "Thursday"],
  ["fri", "Friday"],
  ["sat", "Saturday"],
  ["sun", "Sunday"],
];

const DEFAULT_HOURS: Record<string, string[][]> = {
  mon: [["09:00", "17:00"]],
  tue: [["09:00", "17:00"]],
  wed: [["09:00", "17:00"]],
  thu: [["09:00", "17:00"]],
  fri: [["09:00", "17:00"]],
  sat: [],
  sun: [],
};

export function OperationsPanel({ canManage }: { canManage: boolean }) {
  const { hasFeature } = useAuth();
  const { data, error, mutate } = useApi<OperationsSettings>("/settings/operations");
  const [initialized, setInitialized] = useState(false);
  const [bookingEnabled, setBookingEnabled] = useState(false);
  const [hours, setHours] = useState<Record<string, string[][]>>(DEFAULT_HOURS);
  const [reviewUrl, setReviewUrl] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data && !initialized) {
      setBookingEnabled(data.booking_enabled);
      setHours({ ...DEFAULT_HOURS, ...(data.business_hours ?? {}) });
      setReviewUrl(data.review_url ?? "");
      setInitialized(true);
    }
  }, [data, initialized]);

  const bookingUrl =
    typeof window !== "undefined" && data
      ? `${window.location.origin}/book/${window.localStorage.getItem("vsms.workspace") ?? ""}`
      : "";

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await api("/settings/profile", {
        method: "PATCH",
        body: {
          booking_enabled: bookingEnabled,
          business_hours: hours,
          review_url: reviewUrl.trim() || null,
        },
      });
      toast.success("Operations settings saved");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function setDay(day: string, open: boolean) {
    setHours((current) => ({
      ...current,
      [day]: open ? (current[day]?.length ? current[day] : [["09:00", "17:00"]]) : [],
    }));
  }

  function setRange(day: string, index: number, bound: 0 | 1, value: string) {
    setHours((current) => {
      const ranges = (current[day] ?? []).map((r) => [...r]);
      if (!ranges[index]) return current;
      ranges[index][bound] = value;
      return { ...current, [day]: ranges };
    });
  }

  if (error) return <ErrorState message="Could not load operations settings" retry={() => mutate()} />;
  if (!data) return <LoadingBlock />;

  return (
    <form onSubmit={save} className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Online booking</CardTitle>
          <CardDescription>
            Let customers book an appointment from your public page. Requires the{" "}
            <strong>Online booking</strong> feature on your plan.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!hasFeature("online_booking") && (
            <p className="rounded-lg bg-[var(--muted)] px-3 py-2 text-sm text-[var(--muted-foreground)]">
              Your plan does not include online booking. Upgrade to enable it.
            </p>
          )}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 accent-[var(--brand-primary)]"
              checked={bookingEnabled}
              disabled={!canManage || !hasFeature("online_booking")}
              onChange={(e) => setBookingEnabled(e.target.checked)}
            />
            Accept online bookings
          </label>
          {bookingEnabled && bookingUrl && (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)] p-3">
              <p className="text-xs font-medium">Your booking page</p>
              <div className="mt-1 flex items-center gap-2">
                <code className="truncate text-xs">{bookingUrl}</code>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => copyText(bookingUrl, "Booking link")}
                >
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  Copy
                </Button>
              </div>
            </div>
          )}

          <fieldset className="space-y-2">
            <legend className="text-xs font-medium">Business hours</legend>
            <p className="text-xs text-[var(--muted-foreground)]">
              Slots are generated hourly inside these windows ({data.timezone}).
            </p>
            <div className="space-y-2">
              {DAYS.map(([key, label]) => {
                const ranges = hours[key] ?? [];
                const open = ranges.length > 0;
                return (
                  <div key={key} className="flex flex-wrap items-center gap-3">
                    <label className="flex w-32 items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-[var(--brand-primary)]"
                        checked={open}
                        disabled={!canManage}
                        onChange={(e) => setDay(key, e.target.checked)}
                      />
                      {label}
                    </label>
                    {open ? (
                      <div className="flex items-center gap-2">
                        <Input
                          aria-label={`${label} opening time`}
                          type="time"
                          className="h-8 w-28"
                          value={ranges[0]?.[0] ?? "09:00"}
                          disabled={!canManage}
                          onChange={(e) => setRange(key, 0, 0, e.target.value)}
                        />
                        <span className="text-sm text-[var(--muted-foreground)]">to</span>
                        <Input
                          aria-label={`${label} closing time`}
                          type="time"
                          className="h-8 w-28"
                          value={ranges[0]?.[1] ?? "17:00"}
                          disabled={!canManage}
                          onChange={(e) => setRange(key, 0, 1, e.target.value)}
                        />
                      </div>
                    ) : (
                      <span className="text-sm text-[var(--muted-foreground)]">Closed</span>
                    )}
                  </div>
                );
              })}
            </div>
          </fieldset>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Review requests</CardTitle>
          <CardDescription>
            After a job, ask the customer for feedback and send happy customers to your
            public review page.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field
            label="Public review URL"
            htmlFor="ops-review-url"
            hint="Shown after a customer submits their rating (e.g. your Google review link)."
          >
            <Input
              id="ops-review-url"
              type="url"
              value={reviewUrl}
              disabled={!canManage || !hasFeature("review_requests")}
              onChange={(e) => setReviewUrl(e.target.value)}
              placeholder="https://g.page/r/…/review"
            />
          </Field>
          {!hasFeature("review_requests") && (
            <p className="text-sm text-[var(--muted-foreground)]">
              Your plan does not include review requests.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button type="submit" loading={saving} disabled={!canManage}>
          Save operations settings
        </Button>
      </div>
    </form>
  );
}

const NOTIFICATION_TONES: Record<string, "success" | "danger" | "neutral" | "warning"> = {
  sent: "success",
  failed: "danger",
  skipped: "warning",
  queued: "neutral",
};

type PushDeviceState = "unsupported" | "denied" | "off" | "on";

function PushCard() {
  const { data: config } = useApi<PushConfig>("/push/config");
  const { data: devices, isLoading, mutate } = useApi<PushSubscriptionRow[]>(
    "/push/subscriptions",
  );
  const [state, setState] = useState<PushDeviceState>("off");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!pushSupported()) {
      setState("unsupported");
      return;
    }
    if (Notification.permission === "denied") setState("denied");
    currentDeviceEndpoint()
      .then((endpoint) => setState(endpoint ? "on" : "off"))
      .catch(() => setState("off"));
  }, []);

  const enabled = config?.enabled === true && Boolean(config.public_key);

  async function enable() {
    if (!config?.public_key) return;
    setBusy(true);
    try {
      await subscribeCurrentDevice(config.public_key);
      toast.success("Push notifications enabled on this device");
      setState("on");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: PushSubscriptionRow) {
    setBusy(true);
    try {
      await removePushSubscription(row);
      toast.success("Device removed");
      const endpoint = await currentDeviceEndpoint();
      if (!endpoint) setState("off");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function sendTest() {
    setBusy(true);
    try {
      const result = await api<{ sent: number; failed: number }>("/push/test", {
        body: {},
      });
      if (result.sent > 0 && result.failed === 0) {
        toast.success(
          `Test notification sent to ${result.sent} device${result.sent === 1 ? "" : "s"}`,
        );
      } else if (result.sent > 0) {
        toast.warning(`Sent to ${result.sent}, failed on ${result.failed}`);
      } else if (result.failed > 0) {
        toast.warning(`The push service rejected the test on ${result.failed} device(s)`);
      } else {
        toast.warning("No subscribed devices to send to yet");
      }
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Push notifications on this device</CardTitle>
        <CardDescription>
          Install this app (or keep it open in a browser tab) to get instant alerts about new
          booking requests and orders assigned to you — even when the tab is closed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {state === "unsupported" ? (
          <p className="text-sm text-[var(--muted-foreground)]">
            This browser does not support push notifications. On iPhone and iPad, add the app to
            your Home Screen first.
          </p>
        ) : state === "denied" ? (
          <p className="text-sm text-[var(--muted-foreground)]">
            Notifications are blocked for this site. Allow them in your browser settings, then
            reload this page.
          </p>
        ) : !enabled ? (
          <p className="text-sm text-[var(--muted-foreground)]">
            Push is not available on this deployment yet.
          </p>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {state === "on" ? (
              <Badge tone="success">Enabled on this device</Badge>
            ) : (
              <Button onClick={enable} loading={busy}>
                <BellRing className="h-4 w-4" aria-hidden="true" />
                Enable push notifications
              </Button>
            )}
            {(devices?.length ?? 0) > 0 && (
              <Button variant="secondary" onClick={sendTest} loading={busy}>
                Send test notification
              </Button>
            )}
          </div>
        )}

        {isLoading && !devices ? (
          <TableSkeleton rows={2} cols={3} />
        ) : (devices?.length ?? 0) > 0 ? (
          <Table caption="Devices subscribed to push notifications" className="rounded-lg">
            <THead>
              <TR>
                <TH>Device</TH>
                <TH>Added</TH>
                <TH aria-label="Actions" />
              </TR>
            </THead>
            <TBody>
              {devices?.map((row) => (
                <TR key={row.id}>
                  <TD>
                    <span className="line-clamp-1">
                      {row.user_agent ?? "Unknown device"}
                    </span>
                  </TD>
                  <TD className="whitespace-nowrap text-xs text-[var(--muted-foreground)]">
                    {formatDateTime(row.created_at)}
                  </TD>
                  <TD className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Remove this device"
                      onClick={() => remove(row)}
                      disabled={busy}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function NotificationsPanel({ canManage }: { canManage: boolean }) {
  const { hasFeature } = useAuth();
  const smsEnabled = hasFeature("sms_notifications");
  const { data, error, isLoading, mutate } = useApi<Page<NotificationRow>>(
    smsEnabled ? "/notifications?page_size=50" : null,
  );
  const [channel, setChannel] = useState<"sms" | "email">("sms");
  const [to, setTo] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function sendTest(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("/notifications/test", {
        body: { channel, to: to.trim(), message: message.trim() || null },
      });
      toast.success("Test message sent");
      setMessage("");
      mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <PushCard />
      {!smsEnabled ? (
        <Card>
          <CardHeader>
            <CardTitle>SMS notifications</CardTitle>
            <CardDescription>
              Text customers when their vehicle is ready, when a booking arrives and when an
              invoice is paid.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--muted-foreground)]">
              Your plan does not include SMS notifications. Upgrade to enable them.
            </p>
          </CardContent>
        </Card>
      ) : error ? (
        <ErrorState message="Could not load notifications" retry={() => mutate()} />
      ) : (
        <>
      <Card>
        <CardHeader>
          <CardTitle>Send a test message</CardTitle>
          <CardDescription>
            Confirm your provider is configured. SMS goes through the workshop number;
            email goes through the server&apos;s SMTP relay.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={sendTest}
            className="grid gap-3 sm:grid-cols-[8rem_14rem_1fr_auto] sm:items-end"
          >
            <Field label="Channel" htmlFor="notification-channel" required>
              <Select
                id="notification-channel"
                value={channel}
                onChange={(e) => setChannel(e.target.value as "sms" | "email")}
              >
                <option value="sms">SMS</option>
                <option value="email">Email</option>
              </Select>
            </Field>
            <Field label="To" htmlFor="notification-to" required>
              <Input
                id="notification-to"
                type={channel === "sms" ? "tel" : "email"}
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder={channel === "sms" ? "+1 555 010 0100" : "customer@example.com"}
                required
              />
            </Field>
            <Field label="Message" htmlFor="sms-message">
              <Textarea
                id="sms-message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Leave blank for the default test message"
                className="min-h-9"
              />
            </Field>
            <Button type="submit" loading={busy} disabled={!canManage}>
              <MessageSquare className="h-4 w-4" aria-hidden="true" />
              Send test
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Outbox</CardTitle>
          <CardDescription>The most recent messages, newest first.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && !data ? (
            <TableSkeleton rows={4} cols={4} />
          ) : (data?.items.length ?? 0) === 0 ? (
            <p className="py-6 text-center text-sm text-[var(--muted-foreground)]">
              No messages yet.
            </p>
          ) : (
            <Table caption="Recent messages" className="rounded-lg">
              <THead>
                <TR>
                  <TH>When</TH>
                  <TH>Channel</TH>
                  <TH>To</TH>
                  <TH>Message</TH>
                  <TH>Status</TH>
                </TR>
              </THead>
              <TBody>
                {data?.items.map((row) => (
                  <TR key={row.id}>
                    <TD className="whitespace-nowrap text-xs text-[var(--muted-foreground)]">
                      {formatDateTime(row.created_at)}
                    </TD>
                    <TD className="text-xs uppercase text-[var(--muted-foreground)]">
                      {row.channel}
                    </TD>
                    <TD className="whitespace-nowrap">{row.recipient}</TD>
                    <TD className="max-w-xs">
                      <span className="line-clamp-2">{row.body}</span>
                      {row.error && (
                        <span className="mt-0.5 block text-xs text-[var(--destructive)]">
                          {row.error}
                        </span>
                      )}
                    </TD>
                    <TD>
                      <Badge tone={NOTIFICATION_TONES[row.status] ?? "neutral"}>
                        {titleCase(row.status)}
                      </Badge>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
        </>
      )}
    </div>
  );
}
