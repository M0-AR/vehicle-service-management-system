"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { PageHeader } from "@/components/page";
import { AccountingPanel } from "@/components/settings/accounting-panel";
import { LocationsPanel } from "@/components/settings/locations-panel";
import {
  ApiKeysPanel,
  BillingPanel,
  BrandingPanel,
  DomainsPanel,
  ExportsPanel,
  NotificationsPanel,
  OperationsPanel,
  StaffPanel,
} from "@/components/settings/panels";
import { LoadingBlock } from "@/components/ui/feedback";
import { TabList, TabPanel, type TabDef } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";

function SettingsInner() {
  const params = useSearchParams();
  const { user, hasFeature } = useAuth();

  const role = user?.role ?? "";
  const isTeamAdmin = ["owner", "admin"].includes(role);
  const canViewTeam = ["owner", "admin", "manager"].includes(role);

  const upgrade = params.get("upgrade") ?? undefined;

  const tabs = useMemo<TabDef[]>(() => {
    return [
      { id: "branding", label: "Branding" },
      ...(canViewTeam ? [{ id: "operations", label: "Operations" }] : []),
      ...(canViewTeam ? [{ id: "locations", label: "Locations" }] : []),
      ...(canViewTeam ? [{ id: "notifications", label: "Notifications" }] : []),
      ...(canViewTeam ? [{ id: "staff", label: "Team" }] : []),
      ...(hasFeature("api_access") ? [{ id: "api-keys", label: "API keys" }] : []),
      ...(hasFeature("custom_domain") ? [{ id: "domains", label: "Domains" }] : []),
      ...(canViewTeam && hasFeature("accounting_sync")
        ? [{ id: "accounting", label: "Accounting" }]
        : []),
      { id: "billing", label: "Billing" },
      ...(canViewTeam ? [{ id: "exports", label: "Exports" }] : []),
    ];
  }, [canViewTeam, hasFeature]);

  const requested = params.get("tab");
  const initialTab =
    requested && tabs.some((t) => t.id === requested)
      ? requested
      : upgrade
        ? "billing"
        : "branding";
  const [tab, setTab] = useState(initialTab);

  const active = tabs.some((t) => t.id === tab) ? tab : "branding";

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" description="Workspace, team, billing and data." />
      <TabList tabs={tabs} value={active} onChange={setTab} label="Settings sections" />
      <TabPanel id="branding" value={active}>
        <BrandingPanel canEdit={isTeamAdmin} />
      </TabPanel>
      <TabPanel id="operations" value={active}>
        <OperationsPanel canManage={isTeamAdmin} />
      </TabPanel>
      <TabPanel id="locations" value={active}>
        <LocationsPanel canManage={isTeamAdmin} />
      </TabPanel>
      <TabPanel id="notifications" value={active}>
        <NotificationsPanel canManage={isTeamAdmin} />
      </TabPanel>
      <TabPanel id="staff" value={active}>
        <StaffPanel canManage={isTeamAdmin} />
      </TabPanel>
      <TabPanel id="api-keys" value={active}>
        <ApiKeysPanel canManage={isTeamAdmin} />
      </TabPanel>
      <TabPanel id="domains" value={active}>
        <DomainsPanel />
      </TabPanel>
      <TabPanel id="accounting" value={active}>
        <AccountingPanel />
      </TabPanel>
      <TabPanel id="billing" value={active}>
        <BillingPanel highlight={upgrade} />
      </TabPanel>
      <TabPanel id="exports" value={active}>
        <ExportsPanel />
      </TabPanel>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <SettingsInner />
    </Suspense>
  );
}
