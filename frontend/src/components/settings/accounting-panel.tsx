"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Download, Link2, RefreshCw, Unplug } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/fields";
import { ErrorState, LoadingBlock } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, downloadApiFile, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime, money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type {
  AccountingConnectResult,
  AccountingRun,
  AccountingStatus,
  Page,
} from "@/lib/types";

const PROVIDER_LABEL: Record<string, string> = {
  stub: "Demo accounting",
  quickbooks: "QuickBooks Online",
  xero: "Xero",
};

function isoDate(value: Date): string {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, "0");
  const d = String(value.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function monthStart(): string {
  const now = new Date();
  return isoDate(new Date(now.getFullYear(), now.getMonth(), 1));
}

function runTone(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "danger";
  if (status === "partial") return "warning";
  return "neutral";
}

export function AccountingPanel() {
  const { hasFeature } = useAuth();
  const params = useSearchParams();
  const callbackStarted = useRef(false);
  const [start, setStart] = useState(monthStart);
  const [end, setEnd] = useState(() => isoDate(new Date()));
  const [mapping, setMapping] = useState({ payment: "1000", income: "4000", tax: "2200" });
  const [mappingLoaded, setMappingLoaded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);

  const {
    data,
    error,
    isLoading,
    mutate: mutateStatus,
  } = useApi<AccountingStatus>("/accounting");
  const {
    data: runs,
    error: runsError,
    mutate: mutateRuns,
  } = useApi<Page<AccountingRun>>("/accounting/runs?page_size=10");

  useEffect(() => {
    if (isLoading || !data || mappingLoaded) return;
    setMapping({
      payment: data.connection?.accounts.payment ?? "1000",
      income: data.connection?.accounts.income ?? "4000",
      tax: data.connection?.accounts.tax ?? "2200",
    });
    setMappingLoaded(true);
  }, [data, isLoading, mappingLoaded]);

  useEffect(() => {
    if (callbackStarted.current) return;
    const code = params.get("code");
    const state = params.get("state");
    const oauthError = params.get("error");
    if (!oauthError && (!code || !state)) return;
    callbackStarted.current = true;

    const url = new URL(window.location.href);
    for (const key of ["code", "state", "realmId", "error", "error_description"]) {
      url.searchParams.delete(key);
    }
    window.history.replaceState({}, "", url.toString());

    if (oauthError) {
      toast.error(params.get("error_description") || "The provider declined the connection.");
      return;
    }
    (async () => {
      setBusy("connect");
      try {
        await api<AccountingStatus>("/accounting/callback", {
          body: { code, state, realm_id: params.get("realmId") },
        });
        await Promise.all([mutateStatus(), mutateRuns()]);
        toast.success("Accounting connected");
      } catch (err) {
        toast.error(errorMessage(err));
      } finally {
        setBusy(null);
      }
    })();
  }, [params, mutateStatus, mutateRuns]);

  if (!hasFeature("accounting_sync")) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Accounting sync</CardTitle>
          <CardDescription>
            Post paid invoices to QuickBooks or Xero, or export a mapped journal CSV. Available on
            Pro and Enterprise.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="secondary" onClick={() => (window.location.href = "/app/settings?tab=billing")}>
            Compare plans
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (isLoading) return <LoadingBlock label="Loading accounting settings" />;
  if (error) return <ErrorState message={errorMessage(error)} retry={() => void mutateStatus()} />;

  const status = data!;
  const connection = status.connection;
  const providerLabel = PROVIDER_LABEL[status.provider] ?? status.provider;

  async function connect() {
    setBusy("connect");
    try {
      const result = await api<AccountingConnectResult>("/accounting/connect", { body: {} });
      if (result.authorize_url) {
        window.location.href = result.authorize_url;
        return;
      }
      await Promise.all([mutateStatus(), mutateRuns()]);
      toast.success(result.message);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function saveMapping() {
    setBusy("mapping");
    try {
      await api<AccountingStatus>("/accounting/connection", {
        method: "PATCH",
        body: mapping,
      });
      await mutateStatus();
      toast.success("Account mapping saved");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function disconnect() {
    setBusy("disconnect");
    try {
      await api("/accounting/connection", { method: "DELETE" });
      setConfirmDisconnect(false);
      await Promise.all([mutateStatus(), mutateRuns()]);
      toast.success("Accounting disconnected");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function sync() {
    setBusy("sync");
    try {
      const run = await api<AccountingRun>("/accounting/sync", {
        body: { period_start: start, period_end: end },
      });
      await Promise.all([mutateStatus(), mutateRuns()]);
      if (run.status === "failed") {
        toast.error(run.detail || "Sync failed");
      } else {
        toast.success(
          run.invoices_count === 0
            ? "Nothing new to sync"
            : `Posted ${run.invoices_count} invoice${run.invoices_count === 1 ? "" : "s"}`,
        );
      }
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function exportCsv() {
    setBusy("export");
    try {
      await downloadApiFile(
        `/accounting/export?period_start=${start}&period_end=${end}`,
        `accounting-journal-${start}-${end}.csv`,
      );
      toast.success("Journal CSV downloaded");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Accounting</CardTitle>
              <CardDescription>
                Provider: {providerLabel}. Paid invoices post as journals; nothing is sent until you
                run a sync.
              </CardDescription>
            </div>
            <Badge tone={connection ? "success" : "neutral"}>
              {connection ? "Connected" : "Not connected"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {!status.configured && (
            <div className="rounded-lg border border-[var(--warning)]/40 bg-[var(--warning)]/10 p-3 text-sm">
              {providerLabel} is not configured on this server. Set its client id, secret and
              redirect URI, then reload this page.
            </div>
          )}

          {connection ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--border)] p-3">
              <div className="text-sm">
                <p className="font-medium text-[var(--foreground)]">
                  {PROVIDER_LABEL[connection.provider] ?? connection.provider}
                </p>
                <p className="text-[var(--muted-foreground)]">
                  Company {connection.external_tenant_id ?? "—"} ·{" "}
                  {connection.last_synced_at
                    ? `Last sync ${formatDateTime(connection.last_synced_at)}`
                    : "Never synced"}
                </p>
              </div>
              <Button
                variant="secondary"
                onClick={() => setConfirmDisconnect(true)}
                loading={busy === "disconnect"}
              >
                <Unplug className="h-4 w-4" aria-hidden="true" />
                Disconnect
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-[var(--border)] p-3">
              <p className="text-sm text-[var(--muted-foreground)]">
                {status.provider === "stub"
                  ? "Connect demo accounting to exercise the sync flow without provider credentials."
                  : "Authorise the provider to post journals. Tokens are stored encrypted."}
              </p>
              <Button onClick={connect} loading={busy === "connect"} disabled={!status.configured}>
                <Link2 className="h-4 w-4" aria-hidden="true" />
                Connect provider
              </Button>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Payment / undeposited funds" htmlFor="acct-payment" hint="Debited for each paid invoice.">
              <Input
                id="acct-payment"
                value={mapping.payment}
                onChange={(e) => setMapping({ ...mapping, payment: e.target.value })}
                disabled={!connection}
              />
            </Field>
            <Field label="Service income" htmlFor="acct-income" hint="Credited for the invoice net.">
              <Input
                id="acct-income"
                value={mapping.income}
                onChange={(e) => setMapping({ ...mapping, income: e.target.value })}
                disabled={!connection}
              />
            </Field>
            <Field label="Tax payable" htmlFor="acct-tax" hint="Credited for invoice tax.">
              <Input
                id="acct-tax"
                value={mapping.tax}
                onChange={(e) => setMapping({ ...mapping, tax: e.target.value })}
                disabled={!connection}
              />
            </Field>
          </div>
          <div className="flex justify-end">
            <Button
              variant="secondary"
              onClick={saveMapping}
              loading={busy === "mapping"}
              disabled={
                !connection ||
                !mapping.payment.trim() ||
                !mapping.income.trim() ||
                !mapping.tax.trim()
              }
            >
              Save mapping
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sync paid invoices</CardTitle>
          <CardDescription>
            {status.pending_invoices} paid invoice{status.pending_invoices === 1 ? "" : "s"} not yet
            posted. Re-running a period skips invoices already posted.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="From" htmlFor="acct-start">
              <Input id="acct-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </Field>
            <Field label="To" htmlFor="acct-end" error={end < start ? "End must be after start." : null}>
              <Input id="acct-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={sync} loading={busy === "sync"} disabled={!connection || end < start}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Sync now
            </Button>
            <Button variant="secondary" onClick={exportCsv} loading={busy === "export"} disabled={end < start}>
              <Download className="h-4 w-4" aria-hidden="true" />
              Download journal CSV
            </Button>
          </div>

          {runsError ? (
            <ErrorState message={errorMessage(runsError)} retry={() => void mutateRuns()} />
          ) : runs && runs.items.length > 0 ? (
            <Table caption="Recent accounting sync runs">
              <THead>
                <TR>
                  <TH>Period</TH>
                  <TH>Status</TH>
                  <TH className="text-right">Invoices</TH>
                  <TH className="text-right">Total</TH>
                  <TH>Started</TH>
                </TR>
              </THead>
              <TBody>
                {runs.items.map((run) => (
                  <TR key={run.id}>
                    <TD>
                      {formatDate(run.period_start)} – {formatDate(run.period_end)}
                    </TD>
                    <TD>
                      <Badge tone={runTone(run.status)}>{run.status}</Badge>
                      {run.detail && (
                        <p className="mt-1 max-w-xs truncate text-xs text-[var(--destructive)]" title={run.detail}>
                          {run.detail}
                        </p>
                      )}
                    </TD>
                    <TD className="text-right">{run.invoices_count}</TD>
                    <TD className="text-right">{money(run.total_amount, run.currency)}</TD>
                    <TD>{formatDateTime(run.created_at)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <p className="text-sm text-[var(--muted-foreground)]">No sync runs yet.</p>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={confirmDisconnect}
        onOpenChange={(value) => !value && setConfirmDisconnect(false)}
      >
        <DialogContent
          title="Disconnect accounting?"
          description="Stored provider tokens are deleted. Past sync runs stay in the history, and invoices can be re-synced after reconnecting."
        >
          <p className="text-sm text-[var(--muted-foreground)]">
            You can reconnect at any time without losing past runs.
          </p>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirmDisconnect(false)}>
              Keep connected
            </Button>
            <Button variant="destructive" onClick={disconnect} loading={busy === "disconnect"}>
              Disconnect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
