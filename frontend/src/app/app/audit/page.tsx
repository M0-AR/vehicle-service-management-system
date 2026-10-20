"use client";

import { useMemo, useState } from "react";

import { PageHeader, Pager, SearchInput } from "@/components/page";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState, TableSkeleton, UpgradeNotice } from "@/components/ui/feedback";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import type { AuditEntry, Page } from "@/lib/types";

const PAGE_SIZE = 50;

export default function AuditPage() {
  const { hasFeature, ready } = useAuth();
  const allowed = hasFeature("audit_log");

  const [q, setQ] = useState("");
  const debouncedQ = useDebounced(q);
  const [page, setPage] = useState(1);

  const query = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (debouncedQ) params.set("q", debouncedQ);
    return params.toString();
  }, [page, debouncedQ]);

  const { data, error, isLoading, mutate } = useApi<Page<AuditEntry>>(
    ready && allowed ? `/audit?${query}` : null,
  );

  if (ready && !allowed) {
    return (
      <div className="space-y-5">
        <PageHeader title="Audit log" description="Every action taken in your workspace." />
        <UpgradeNotice
          feature="The audit log"
          detail="Keep a complete, searchable record of who changed what — available on the Pro plan."
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Audit log" description="Every action taken in your workspace." />

      <SearchInput
        value={q}
        onChange={(v) => {
          setQ(v);
          setPage(1);
        }}
        placeholder="Search action, entity, user…"
        label="Search audit log"
        className="sm:max-w-xs"
      />

      {error && <ErrorState message="Could not load the audit log" retry={() => mutate()} />}
      {isLoading && !data && <TableSkeleton rows={8} cols={5} />}

      {data && data.items.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-[var(--muted-foreground)]">
            No audit entries match your search.
          </CardContent>
        </Card>
      )}

      {data && data.items.length > 0 && (
        <>
          <Table caption="Audit log">
            <THead>
              <TR>
                <TH>When</TH>
                <TH>User</TH>
                <TH>Action</TH>
                <TH>Entity</TH>
                <TH className="hidden sm:table-cell">IP</TH>
              </TR>
            </THead>
            <TBody>
              {data.items.map((entry) => (
                <TR key={entry.id}>
                  <TD className="whitespace-nowrap text-[var(--muted-foreground)]">
                    {formatDateTime(entry.created_at)}
                  </TD>
                  <TD>{entry.user_name ?? "System"}</TD>
                  <TD className="font-medium">{entry.action}</TD>
                  <TD className="text-[var(--muted-foreground)]">
                    {entry.entity}
                    {entry.entity_id ? ` #${entry.entity_id.slice(0, 8)}` : ""}
                  </TD>
                  <TD className="hidden text-[var(--muted-foreground)] sm:table-cell">
                    {entry.ip ?? "—"}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pager page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} />
        </>
      )}
    </div>
  );
}
