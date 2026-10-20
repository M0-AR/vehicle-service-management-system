"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Eye,
  Megaphone,
  Plus,
  Send,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader, Pager } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/fields";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type {
  Campaign,
  CampaignChannel,
  CampaignDetail,
  CampaignPreview,
  CampaignSegment,
  Page,
} from "@/lib/types";

const PAGE_SIZE = 25;

const SEGMENT_LABELS: Record<CampaignSegment, string> = {
  all: "All customers",
  inactive: "Inactive customers",
  due_service: "Due for service",
};

const SEGMENT_HELP: Record<CampaignSegment, string> = {
  all: "Every customer with a contact for the chosen channel.",
  inactive: "Customers who have not booked anything in the lookback window.",
  due_service: "Customers whose last completed service is older than the lookback window.",
};

const DEFAULT_LOOKBACK: Record<CampaignSegment, number> = {
  all: 90,
  inactive: 90,
  due_service: 180,
};

const CHANNEL_HELP: Record<CampaignChannel, string> = {
  sms: "Sent to each customer's phone number. Requires an SMS provider.",
  email: "Sent to each customer's email address. Requires an email provider.",
};

type Form = {
  name: string;
  channel: CampaignChannel;
  segment: CampaignSegment;
  lookback_days: string;
  body: string;
};

const EMPTY_FORM: Form = {
  name: "",
  channel: "sms",
  segment: "all",
  lookback_days: String(DEFAULT_LOOKBACK.all),
  body: "Hi {name}, it's time for your next service at {shop}. Reply or call us to book.",
};

function resultTone(campaign: Campaign): "neutral" | "success" | "warning" | "danger" {
  if (campaign.status === "draft") return "neutral";
  if (campaign.failed_count > 0) return "danger";
  if (campaign.sent_count > 0 && campaign.skipped_count === 0) return "success";
  if (campaign.sent_count > 0) return "warning";
  return "warning";
}

function resultsLabel(campaign: Campaign): string {
  if (campaign.status === "draft") return "—";
  const parts = [`${campaign.sent_count} sent`];
  if (campaign.skipped_count > 0) parts.push(`${campaign.skipped_count} skipped`);
  if (campaign.failed_count > 0) parts.push(`${campaign.failed_count} failed`);
  return parts.join(" · ");
}

export default function MarketingPage() {
  const { user, hasFeature } = useAuth();
  const role = user?.role ?? "";
  const canWrite = ["owner", "admin"].includes(role);
  const enabled = hasFeature("marketing");

  const [page, setPage] = useState(1);
  const campaigns = useApi<Page<Campaign>>(
    enabled ? `/campaigns?page=${page}&page_size=${PAGE_SIZE}` : null,
  );

  // --- create dialog -------------------------------------------------------
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [preview, setPreview] = useState<CampaignPreview | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const previewSeq = useRef(0);

  // --- send / detail / delete ---------------------------------------------
  const [sendTarget, setSendTarget] = useState<Campaign | null>(null);
  const [sendPreview, setSendPreview] = useState<CampaignPreview | null>(null);
  const [sending, setSending] = useState(false);
  const [viewing, setViewing] = useState<Campaign | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Campaign | null>(null);
  const [deleting, setDeleting] = useState(false);

  const detail = useApi<CampaignDetail>(viewing ? `/campaigns/${viewing.id}` : null);

  const previewQuery = useMemo(() => {
    if (!open) return null;
    return {
      channel: form.channel,
      segment: form.segment,
      lookback_days: Number.parseInt(form.lookback_days, 10) || 90,
    };
  }, [open, form.channel, form.segment, form.lookback_days]);

  useEffect(() => {
    if (!previewQuery) {
      setPreview(null);
      return;
    }
    const seq = ++previewSeq.current;
    setPreviewBusy(true);
    const timer = setTimeout(async () => {
      try {
        const result = await api<CampaignPreview>("/campaigns/preview", {
          body: previewQuery,
        });
        if (seq === previewSeq.current) setPreview(result);
      } catch {
        if (seq === previewSeq.current) setPreview(null);
      } finally {
        if (seq === previewSeq.current) setPreviewBusy(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [previewQuery]);

  useEffect(() => {
    if (!sendTarget) {
      setSendPreview(null);
      return;
    }
    let cancelled = false;
    setSendPreview(null);
    api<CampaignPreview>("/campaigns/preview", {
      body: {
        channel: sendTarget.channel,
        segment: sendTarget.segment,
        lookback_days: sendTarget.lookback_days,
      },
    })
      .then((result) => {
        if (!cancelled) setSendPreview(result);
      })
      .catch(() => {
        if (!cancelled) setSendPreview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sendTarget]);

  function openCreate() {
    setForm(EMPTY_FORM);
    setFormError(null);
    setPreview(null);
    setOpen(true);
  }

  function setSegment(segment: CampaignSegment) {
    setForm((prev) => ({
      ...prev,
      segment,
      lookback_days: String(DEFAULT_LOOKBACK[segment]),
    }));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await api<Campaign>("/campaigns", {
        body: {
          name: form.name.trim(),
          channel: form.channel,
          segment: form.segment,
          lookback_days: Number.parseInt(form.lookback_days, 10) || 90,
          body: form.body.trim(),
        },
      });
      toast.success("Campaign draft created");
      setOpen(false);
      campaigns.mutate();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function send() {
    if (!sendTarget) return;
    setSending(true);
    try {
      const result = await api<Campaign>(`/campaigns/${sendTarget.id}/send`, {
        method: "POST",
      });
      if (result.failed_count > 0) {
        toast.error(
          `${result.failed_count} of ${result.recipients_count} messages failed. Open the campaign for details.`,
        );
      } else if (result.sent_count === 0 && result.skipped_count > 0) {
        toast.warning(
          `Recorded ${result.skipped_count} recipients, but no provider is configured — set one up in Settings → Notifications.`,
        );
      } else if (result.skipped_count > 0) {
        toast.success(
          `Sent to ${result.sent_count} customers (${result.skipped_count} skipped — no provider or contact).`,
        );
      } else {
        toast.success(`Sent to ${result.sent_count} customers`);
      }
      setSendTarget(null);
      campaigns.mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSending(false);
    }
  }

  async function remove() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api(`/campaigns/${deleteTarget.id}`, { method: "DELETE" });
      toast.success("Draft deleted");
      setDeleteTarget(null);
      campaigns.mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setDeleting(false);
    }
  }

  if (!enabled) {
    return (
      <div className="space-y-6">
        <PageHeader title="Marketing" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Megaphone className="h-8 w-8 text-[var(--muted-foreground)]" aria-hidden="true" />
            <p className="text-sm font-medium">Marketing campaigns are available on Pro and Enterprise.</p>
            <p className="max-w-sm text-sm text-[var(--muted-foreground)]">
              Reach inactive customers and vehicles due for service with one message,
              delivered through your SMS or email provider.
            </p>
            <Button onClick={() => (window.location.href = "/app/settings")}>
              View plans
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const total = campaigns.data?.total ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Marketing"
        description="One-shot SMS or email campaigns to customer segments."
      >
        {canWrite && (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" /> New campaign
          </Button>
        )}
      </PageHeader>

      {campaigns.error ? (
        <ErrorState message={errorMessage(campaigns.error)} retry={() => campaigns.mutate()} />
      ) : campaigns.isLoading ? (
        <TableSkeleton cols={6} />
      ) : total === 0 ? (
        <EmptyState
          title="No campaigns yet"
          description="Create a draft, preview the audience, then send it once."
          action={canWrite ? <Button onClick={openCreate}>New campaign</Button> : undefined}
        />
      ) : (
        <>
          <Table caption="Marketing campaigns">
            <THead>
              <TR>
                <TH>Campaign</TH>
                <TH>Audience</TH>
                <TH>Channel</TH>
                <TH>Status</TH>
                <TH>Results</TH>
                <TH>Created</TH>
                <TH className="text-right">Actions</TH>
              </TR>
            </THead>
            <TBody>
              {campaigns.data?.items.map((campaign) => (
                <TR key={campaign.id}>
                  <TD>
                    <div className="font-medium">{campaign.name}</div>
                    <div className="max-w-xs truncate text-xs text-[var(--muted-foreground)]">
                      {campaign.body}
                    </div>
                  </TD>
                  <TD className="text-[var(--muted-foreground)]">
                    {SEGMENT_LABELS[campaign.segment]}
                    {campaign.segment !== "all" && (
                      <span className="text-xs"> · {campaign.lookback_days}d</span>
                    )}
                  </TD>
                  <TD>
                    <Badge tone="brand">{campaign.channel === "sms" ? "SMS" : "Email"}</Badge>
                  </TD>
                  <TD>
                    <Badge tone={campaign.status === "sent" ? "success" : "neutral"}>
                      {titleCase(campaign.status)}
                    </Badge>
                  </TD>
                  <TD>
                    <span
                      className={
                        campaign.failed_count > 0
                          ? "text-[var(--destructive)]"
                          : "text-[var(--muted-foreground)]"
                      }
                    >
                      {resultsLabel(campaign)}
                    </span>
                  </TD>
                  <TD className="text-[var(--muted-foreground)]">
                    {formatDate(campaign.created_at)}
                  </TD>
                  <TD className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`View ${campaign.name}`}
                        onClick={() => setViewing(campaign)}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      {canWrite && campaign.status === "draft" && (
                        <>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Send ${campaign.name}`}
                            onClick={() => setSendTarget(campaign)}
                          >
                            <Send className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Delete ${campaign.name}`}
                            onClick={() => setDeleteTarget(campaign)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </>
                      )}
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
        </>
      )}

      {/* create */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title="New campaign"
          description="Drafts can be reviewed and sent once. Sent campaigns are kept for history."
          wide
        >
          <form onSubmit={save} className="space-y-4">
            <Field label="Name" htmlFor="campaign-name">
              <Input
                id="campaign-name"
                value={form.name}
                onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="Winter service reminder"
                required
                maxLength={120}
              />
            </Field>

            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Channel" htmlFor="campaign-channel" hint={CHANNEL_HELP[form.channel]}>
                <Select
                  id="campaign-channel"
                  value={form.channel}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      channel: e.target.value as CampaignChannel,
                    }))
                  }
                >
                  <option value="sms">SMS</option>
                  <option value="email">Email</option>
                </Select>
              </Field>
              <Field label="Segment" htmlFor="campaign-segment" hint={SEGMENT_HELP[form.segment]}>
                <Select
                  id="campaign-segment"
                  value={form.segment}
                  onChange={(e) => setSegment(e.target.value as CampaignSegment)}
                >
                  {Object.entries(SEGMENT_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              {form.segment !== "all" && (
                <Field
                  label="Lookback (days)"
                  htmlFor="campaign-lookback"
                  hint={
                    form.segment === "inactive"
                      ? "No order created within this window."
                      : "Last completed service older than this window."
                  }
                >
                  <Input
                    id="campaign-lookback"
                    type="number"
                    min={7}
                    max={730}
                    value={form.lookback_days}
                    onChange={(e) =>
                      setForm((prev) => ({ ...prev, lookback_days: e.target.value }))
                    }
                    required
                  />
                </Field>
              )}
            </div>

            <Field
              label="Message"
              htmlFor="campaign-body"
              hint="{name} is replaced with the customer's name and {shop} with your workshop name."
            >
              <Textarea
                id="campaign-body"
                value={form.body}
                onChange={(e) => setForm((prev) => ({ ...prev, body: e.target.value }))}
                rows={4}
                required
                maxLength={1600}
              />
            </Field>

            <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm">
              {previewBusy ? (
                <span className="text-[var(--muted-foreground)]">Counting audience…</span>
              ) : preview ? (
                preview.recipients_count > 0 ? (
                  <span>
                    Reaches <strong>{preview.recipients_count}</strong> of{" "}
                    {preview.customers_count} customers in this segment
                    {preview.recipients_count < preview.customers_count &&
                      " (rest have no contact for this channel)"}
                    .
                  </span>
                ) : (
                  <span className="text-[var(--muted-foreground)]">
                    No customers in this segment can be reached on this channel.
                  </span>
                )
              ) : (
                <span className="text-[var(--muted-foreground)]">
                  Audience preview unavailable — adjust the segment and try again.
                </span>
              )}
            </div>

            {formError && (
              <p className="text-sm text-[var(--destructive)]" role="alert">
                {formError}
              </p>
            )}

            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button
                type="submit"
                loading={saving}
                disabled={previewBusy || preview?.recipients_count === 0}
              >
                Save draft
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* send confirm */}
      <Dialog open={Boolean(sendTarget)} onOpenChange={(next) => !next && setSendTarget(null)}>
        <DialogContent
          title={`Send "${sendTarget?.name ?? ""}"`}
          description="Sending is one-shot; each recipient gets one message through the notification outbox."
        >
          <div className="space-y-3 text-sm">
            <p>
              {sendPreview
                ? `This will reach ${sendPreview.recipients_count} customer${
                    sendPreview.recipients_count === 1 ? "" : "s"
                  } by ${sendTarget?.channel === "sms" ? "SMS" : "email"}.`
                : "Counting the audience…"}
            </p>
            <p className="text-[var(--muted-foreground)]">
              Without a configured provider the messages are recorded as skipped, not failed.
            </p>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setSendTarget(null)}>
              Cancel
            </Button>
            <Button
              onClick={send}
              loading={sending}
              disabled={!sendPreview || sendPreview.recipients_count === 0}
            >
              <Send className="h-4 w-4" aria-hidden="true" /> Send now
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* detail */}
      <Dialog open={Boolean(viewing)} onOpenChange={(next) => !next && setViewing(null)}>
        <DialogContent title={viewing?.name ?? "Campaign"} description={viewing?.body} wide>
          {detail.error ? (
            <ErrorState message={errorMessage(detail.error)} retry={() => detail.mutate()} />
          ) : detail.isLoading ? (
            <TableSkeleton cols={3} />
          ) : detail.data ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-[var(--muted-foreground)]">
                    Audience
                  </p>
                  <p className="mt-1 font-medium">
                    {SEGMENT_LABELS[detail.data.segment]}
                    {detail.data.segment !== "all" && ` · ${detail.data.lookback_days}d`}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-[var(--muted-foreground)]">
                    Status
                  </p>
                  <p className="mt-1">
                    <Badge tone={detail.data.status === "sent" ? "success" : "neutral"}>
                      {titleCase(detail.data.status)}
                    </Badge>
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-[var(--muted-foreground)]">
                    Sent / skipped / failed
                  </p>
                  <p className="mt-1 font-medium tabular-nums">
                    {detail.data.sent_count} / {detail.data.skipped_count} /{" "}
                    {detail.data.failed_count}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-[var(--muted-foreground)]">
                    Sent at
                  </p>
                  <p className="mt-1">{detail.data.sent_at ? formatDate(detail.data.sent_at) : "—"}</p>
                </div>
              </div>

              {detail.data.recipients.length > 0 ? (
                <div className="max-h-80 overflow-y-auto rounded-lg border border-[var(--border)]">
                  <Table caption="Campaign recipients">
                    <THead>
                      <TR>
                        <TH>Recipient</TH>
                        <TH>Status</TH>
                        <TH>Detail</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {detail.data.recipients.map((recipient) => (
                        <TR key={recipient.id}>
                          <TD className="font-medium">{recipient.recipient}</TD>
                          <TD>
                            <Badge
                              tone={
                                recipient.status === "sent"
                                  ? "success"
                                  : recipient.status === "failed"
                                    ? "danger"
                                    : recipient.status === "skipped"
                                      ? "warning"
                                      : "neutral"
                              }
                            >
                              {titleCase(recipient.status)}
                            </Badge>
                          </TD>
                          <TD className="text-[var(--muted-foreground)]">
                            {recipient.error ?? "—"}
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </div>
              ) : (
                <p className="text-sm text-[var(--muted-foreground)]">
                  No recipients recorded yet — send the draft to deliver it.
                </p>
              )}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* delete confirm */}
      <Dialog
        open={Boolean(deleteTarget)}
        onOpenChange={(next) => !next && setDeleteTarget(null)}
      >
        <DialogContent
          title={`Delete "${deleteTarget?.name ?? ""}"?`}
          description="Only drafts can be deleted. This cannot be undone."
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={remove} loading={deleting}>
              Delete draft
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
