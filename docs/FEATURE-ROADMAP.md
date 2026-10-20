# Feature roadmap — competitive gap analysis

Basis: the 2026 vendor scan and research batch (S1–S10, notes in /tmp/opencode/ui-research),
cross-checked against our shipped backend (`backend/app/api/routers/`: audit, auth, customers,
dashboard, health, invoices, orders, public, settings, staff, vehicles, webhooks).

## 1. What we ship today

Multi-tenant workspaces (RLS-isolated), auth + roles (owner/manager/mechanic/viewer), staff,
customers, vehicles, service orders with line items + status workflow, invoices with payment
marking, dashboard KPIs, audit log, CSV exports, white-label branding, plan entitlements.

## 2. Gaps vs the 2026 market

Recurring across the vendor scan — expected by buyers, absent here:

| # | Feature | Evidence / why it matters | Status |
|---|---|---|---|
| 1 | Digital vehicle inspection (DVI, photos) | Top adoption driver in 2026 vendor positioning | shipped (Tier B) |
| 2 | Estimates/quotes + online approval | Standard flow (draft → approve → order); landing copy already promises "Build estimates" | shipped (Tier A) |
| 3 | VIN lookup on intake | Table stakes; NHTSA vPIC decode is a free, keyless API | shipped (Tier A) |
| 4 | Online booking | Standard on most vendors; no public scheduling today | shipped (Tier B) |
| 5 | Customer portal / status link | Customers expect a link, not a login | shipped (Tier A) |
| 6 | Card payments (Stripe) | Manual "mark paid" only today | shipped (Tier B) |
| 7 | SMS reminders / status texts | Standard notification channel; no SMS integration in backend | shipped (Tier B) |
| 8 | Review / reputation requests | Common post-service automation | shipped (Tier B) |
| 9 | Inventory & parts management | Parts are free-text line items; no stock/cost tracking | shipped (Tier C) |
| 10 | Parts supplier integrations | Regional expectation (e.g. PartsTech in US) | shipped (Tier C) |
| 11 | Accounting sync (QuickBooks/Xero) | CSV export is the only path today | shipped (Tier C) |
| 12 | Marketing / CRM automation | Reminder campaigns, follow-ups | shipped (Tier C) |
| 13 | Multi-location per tenant | Multi-tenant ≠ multi-location; growth-tier expectation | shipped (Tier C) |
| 14 | Mobile app / PWA | `/offline` route exists; installability/manifest unverified | shipped (Tier C) |
| 15 | Work order / invoice print & PDF | No print stylesheet verified | shipped (Tier A) |

## 3. Prioritized plan

### Tier A — convert on the landing page, low effort — ✅ shipped

1. **Public plans API + pricing consistency.** `GET /api/v1/public/plans`; landing and signup read
   the catalog ($0 Free / $29 Pro / $99 Enterprise) through `usePlans()` + `PricingGrid`; the old
   hardcoded `$49` is gone.
2. **Estimates → approval links.** `estimates` + `estimate_items` (RLS), `ES-` numbering,
   draft→sent→approved/declined, token link (`/estimate/{token}`), atomic approve that creates a
   service order with copied items (`converted_order_id`), audit entries for send/approve/decline.
   Staff UI at `/app/estimates` and `/app/estimates/[id]`.
3. **VIN decode on vehicle create.** `GET /api/v1/vehicles/decode-vin` proxies NHTSA vPIC, validates
   the 17-character shape, and autofills make/model/year/fuel in the add-vehicle dialog.
4. **Customer status link.** RLS-free `public_links` registry, `POST/DELETE
   /service-orders/{id}/share`, public `/status/{token}` page with status timeline, vehicle,
   schedule and line items — deliberately no prices.
5. **Print stylesheet.** `@media print` in `globals.css` strips app chrome and flattens dialogs;
   Print buttons on order detail, estimate detail and the invoice preview.

Verification: `backend/tests/test_features.py` (5 tests) → suite **20 passed**; frontend
`typecheck` + `build` clean; browser E2E on the demo tenant covered pricing, estimate
send→approve→order, status link + revoke/invalid token, and live VIN decode.

### Tier B — table stakes, medium effort — ✅ shipped

6. **Stripe payments** on invoices (payment links + webhook updates status; entitlement-gated).
   `POST /invoices/{id}/payment-link` → Checkout session + `payment_url`; webhook marks paid
   idempotently; 409 with setup guidance when no provider is configured.
7. **SMS notifications** (Twilio-class provider): booking confirmations, "ready for pickup", review
   links, invoice paid. Outbox records every message (`sent`/`failed`/`skipped`); skipped when the
   provider is unconfigured; staff test form in Settings → Notifications.
8. **DVI checklists with photos** (new models; ties into order detail and the customer status link).
   One inspection per order, condition chips (`ok`/`attention`/`critical`/`na`), notes, JPEG/PNG/WebP
   uploads (8MB, magic-byte checked) served through authed and token-scoped routes.
9. **Online booking** (public availability page → scheduled order; ties staff + upcoming view).
   Hourly slots from tenant business hours (14 days, capacity 2/hour, 2h lead), honeypot + rate
   limits, creates customer/vehicle/order and a `BookingRequest`; confirmation SMS.
10. **Review request** after completion (email → later Google review link). Tokenized
    `/review/{token}` page, star rating + comment, thank-you links to the workspace review URL;
    re-request rotates the token and re-sends the SMS.

Verification: `backend/tests/test_tier_b.py` (7 tests) → suite **27 passed**; frontend
`typecheck` + `build` clean; `alembic current` = `0003 (head)`; browser E2E on the demo tenant
covered booking → `SO-00016`/`SO-00017`, review request → 5-star submission, DVI with photo +
public status rendering, and the invoice payment-link 409 guidance.

### Tier C — depth / integrations (in progress)

11. **Inventory + parts catalog** (stock, reorder, cost → margin in dashboard) — ✅ **shipped**:
    `parts` + append-only `stock_movements` ledger with FORCE RLS, auto SKU, low-stock filter and
    summary endpoints; order line items link `service_items.part_id`, issue stock on add and return
    it on remove/cancel; `inventory` entitlement (pro/enterprise) added by migration `0004`.
    Verified by `backend/tests/test_inventory.py` (suite **31 passed**) and browser E2E on the demo
    tenant (`/app/inventory`, `SO-00018`: autofill, adjust in/out, low-stock badge/filter, cancel
    reconciliation). Details in `docs/UI-REDESIGN.md` §16.
12. **Accounting sync** (QuickBooks/Xero OAuth) — ✅ **shipped**: one connection per tenant; the
    provider is fixed per deployment (`ACCOUNTING_PROVIDER=stub|quickbooks|xero`, default `stub`);
    paid invoices post as journals (debit payment/undeposited funds, credit income + tax) to QBO
    `JournalEntry` / Xero `ManualJournal`, tokens AES-GCM-encrypted, per-run idempotency via synced
    items, and a mapped journal CSV export for keyless use. `accounting_sync` entitlement
    (pro/enterprise) added by migration `0005`. Verified by `backend/tests/test_accounting.py`
    (suite **35 passed**) and browser E2E on the demo tenant (stub connect → sync → idempotent
    re-sync → CSV → disconnect). Details in `docs/UI-REDESIGN.md` §17.
13. **Marketing campaigns** — ✅ **shipped**: one-shot SMS/email campaigns over computed
    segments (`all`, `inactive` — no order in N days, `due_service` — last completed service older
    than N days), audience preview before save, capped at 500 recipients, delivery through the
    existing notification outbox (unconfigured providers record `skipped` rows), per-recipient
    status/error detail, and `campaign.created|sent|deleted` audit entries. `marketing`
    entitlement (pro/enterprise) added by migration `0006`. Email delivery is real since the
    SMTP channel landed (`docs/UI-REDESIGN.md` §22; skipped only when `SMTP_HOST`/`SMTP_FROM` are
    unset). Verified by `backend/tests/test_campaigns.py` and `backend/tests/test_email.py`
    (suite **58 passed**) and browser E2E on the demo tenant (draft → live preview → send with
    skipped rows → detail). Details in `docs/UI-REDESIGN.md` §18.
14. **Multi-location per tenant** — ✅ **shipped**: `locations` branches (FORCE RLS, unique
    name per tenant, one default enforced in service) with CRUD rules (last/default/referenced
    deletes refused, unsetting the default refused); `service_orders.location_id` assigned from
    the payload or the tenant default on create; orders list gains a Location column, a
    `location_id` filter and a Location select in the create/edit dialogs; Settings → Locations
    panel (owner/admin write, manager read). Customers and vehicles stay shared across branches;
    inventory/staff scheduling remain tenant-wide in v1. No plan gate — workflow depth, not an
    entitlement. Migration `0007` seeds "Main location" for existing tenants and backfills
    orders; provisioning creates it for new tenants. Verified by `backend/tests/test_locations.py`
    (suite **44 passed**) and browser E2E on the demo tenant (add/star/delete guards, pre-filled
    create, filter, detail edit). Details in `docs/UI-REDESIGN.md` §19.
15. **PWA installability + staff push notifications** — ✅ **shipped**: manifest completed
    (`id`, `categories`, `prefer_related_applications: false`, iOS icon) on top of the existing
    service worker/offline page; Web Push with deployment-wide VAPID keys (env or auto-generated
    once in `push_config`, encrypted at rest) and per-device `push_subscriptions` (FORCE RLS).
    Settings → Notifications gains the enable/blocked/off states, device list with remove, and a
    send-test that reports sent/failed. Triggers v1: public booking → owner/admin/manager, order
    assigned/reassigned → that mechanic. No plan gate (no paid provider involved). Migration
    `0008`. Verified by `backend/tests/test_push.py` (suite **49 passed**) and prod-build browser
    E2E (installability, offline fallback, encrypted delivery to a local receiver for test,
    booking and assignment flows). Details in `docs/UI-REDESIGN.md` §20.
16. **Parts supplier catalog** — ✅ **shipped**: a provider seam with two keyless providers —
    `stub` (built-in demo distributor) and `csv` (tenant-uploaded price list; header
    `sku,description` required, optional `brand,cost,price,stock`; upsert on SKU; 2 MB /
    5,000-row cap). Connections carry an optional portal URL and offer rows link there, so the
    buyer orders at the supplier (no PO transmission in v1; PartsTech/NexPart/WHI APIs are
    partner-gated). Search runs across every connection and Import upserts the inventory part by
    SKU (create at stock 0, or update brand/supplier/cost/price). `suppliers` entitlement
    (pro/enterprise) via migration `0009`. Verified by `backend/tests/test_suppliers.py` (suite
    **53 passed**) and prod-build browser E2E (add connection → CSV import with skipped rows →
    search → import → inventory). Details in `docs/UI-REDESIGN.md` §21.

## 4. Security & platform hardening queue

- **Access token storage**: currently localStorage (`frontend/src/lib/api.ts:24-30`). Move to
  memory-only + boot refresh via the HttpOnly cookie; because `/auth/refresh` rotates the refresh
  token on every call, add a BroadcastChannel/grace window so two booting tabs cannot race each
  other out of the session. Verified behavior recorded in `docs/UI-REDESIGN.md` §13.3.
- Frontend error monitoring + CWV budget in CI (LCP ≤2.5s, INP ≤200ms, CLS ≤0.1 — S5/S7).
- Frontend test harness (none today; S5 gap) — start with auth/session and orders flow.
- **Security headers** — ✅ shipped 2026-10-19: baseline CSP + nosniff/frame/referrer/
  permissions headers at Caddy and Next, HSTS on TLS sites (see RUNBOOK → Security headers).
  Auth rate-limit review (2026-10-19): login is 10/min per tenant+IP; every other `/api/*`
  request sits behind the 600/min pre-auth bucket per tenant/IP/prefix plus the authenticated
  per-plan limit — no gap found, no change needed. Remaining: periodic CSP audit when
  third-party origins are added.

## 5. Guardrails for new features

Spec first (this file / `docs/UI-REDESIGN.md`), backend pytest coverage, audit-log entries,
RBAC + RLS tenant scoping (all queries), plan-entitlements gating, reuse of the UI kit,
contrast (AA) + keyboard acceptance, README/RUNBOOK updates.

## 6. Copy fixes to bundle with P6

- Landing: `$49` → plans API; "Quotes & invoicing" → say "Invoices" until estimates ship;
  add Enterprise tier; hero screenshot capture.
