# ARCHITECTURE — Vehicle Service Management System

A multi-tenant SaaS for auto-service businesses: vehicles, customers, mechanics,
service orders, invoices, dashboards — one deployment serving many tenants with
hard data isolation, white-labeling, plan entitlements and per-tenant throttling.

## Topology

```
                        ┌────────────────────────┐
  Internet ────────────►│         Caddy          │ :80/:443  TLS + routing
                        │  (on-demand TLS, ask)  │
                        └─────┬────────────┬─────┘
                       /api/* │            │ everything else
                              ▼            ▼
                       ┌────────────┐ ┌────────────┐
                       │  backend   │ │  frontend  │
                       │  FastAPI   │ │ Next.js 16 │
                       │   :8000    │ │   :3000    │
                       └──┬──────┬──┘ └────────────┘
                          ▼      ▼
                     ┌────────┐ ┌───────┐
                     │postgres│ │ redis │     private network only
                     └────────┘ └───────┘
```

Networks: `edge` (caddy ↔ frontend/backend) and `backend` (`internal: true`).
Only Caddy publishes ports.

## Multi-tenancy request flow (pool model)

1. Browser hits `https://acme.example.com` (subdomain) or `https://shop.customer.com`
   (verified custom domain) → Caddy → frontend (HTML) / backend (API).
2. Backend `TenantResolutionMiddleware` derives *routing hints* from the Host
   header (`slug` / `domain`) — used **only** to resolve which tenant a login page
   or signup refers to. It is never trusted for data access.
3. Login → tenant resolved (slug/domain/availability API) → JWT with
   `tenant` claim + short expiry. Every subsequent request is authorized from the
   **signed JWT**, not headers.
4. `get_auth_context` opens one transaction and executes
   `set_config('app.current_tenant', :t, true)` + `set_config('app.current_user', :u, true)`
   — **transaction-scoped** (pooler-safe; context dies with the transaction).
5. All ORM queries then run under Postgres RLS: policy
   `USING (tenant_id = current_setting('app.current_tenant')::uuid)` with
   `WITH CHECK` for writes, on every business table, with `FORCE ROW LEVEL SECURITY`.
6. Fail-closed: missing/empty GUC → `NULLIF(current_setting(...), '')` → NULL →
   `tenant_id = NULL` is false → zero rows visible, writes rejected.
7. Runtime DB role is `app_user` (NOSUPERUSER, NOBYPASSRLS, not table owner) so
   RLS cannot be bypassed by accident or by a compromised app.

### Isolation tiers (hybrid)

`tenants.isolation_tier` = `pool` (default) | `silo`.
`tenants.region` selects the regional database via `REGION_DATABASE_URLS`
(JSON map region → URL; empty = single region). Provisioning records both, so a
tenant can be moved to a dedicated database/region without API changes —
residency answer for GDPR-style requirements.

## Domain model (all tenant tables carry `tenant_id uuid NOT NULL`)

| Table | Purpose |
|---|---|
| `tenants` (registry, no RLS) | slug, name, plan, status, region, isolation_tier, encryption_mode |
| `tenant_domains` (registry) | custom domain → tenant (public routing data, like DNS) |
| `tenant_settings` | currency, timezone, tax_rate, brand JSONB, features JSONB |
| `users` | tenant staff: role owner/admin/manager/mechanic/viewer |
| `refresh_tokens` | opaque, hashed at rest, rotated |
| `customers` | vehicle owners |
| `vehicles` | plate, make, model, year, VIN, fuel, mileage, status, owner FK |
| `service_orders` | number, vehicle, customer, mechanic, status lifecycle, priority, costs, schedule, `location_id` |
| `locations` | branches per tenant: name (unique), address, phone, one default (auto-provisioned) |
| `service_items` | order lines: labor / part, qty, unit price, optional `part_id` link |
| `invoices` | issued from orders, status draft/sent/paid/overdue/void, snapshot lines |
| `parts` | catalog: SKU, name, category, brand/supplier, cost/price, stock_qty, reorder_level, active |
| `stock_movements` | append-only ledger: part, signed delta, reason (received/issued/returned/adjustment), note, order/user refs |
| `supplier_connections` | distributor link per tenant: name (unique), provider `stub|csv`, optional order portal URL |
| `supplier_catalog_items` | uploaded offers per connection: SKU (unique per connection), description, brand, cost/price, stock |
| `audit_logs` | who did what, when, to which entity (tenant-scoped) |
| `api_keys` | hashed keys for the `api_access` entitlement |
| `billing_accounts`, `billing_events` | provider-agnostic subscription state + webhook log |
| `tenant_keys` | BYOK: wrapped per-tenant DEKs (envelope encryption) |
| `plans` (registry) | catalog: price, currency, limits, features |
| `estimates`, `estimate_items` | quote draft → sent → approved/declined, converts to an order |
| `public_links` (registry) | tokenized status / estimate / review links (rotation + revoke) |
| `inspections` | one DVI per order: items JSONB (status, note, photos) + completed_at |
| `notifications` | SMS outbox: template, body, provider status `sent/failed/skipped` |
| `bookings` | public booking requests → customer/vehicle/order conversion |
| `review_requests`, `reviews` | tokenized post-service rating + comment |
| `accounting_connections` | one per tenant: provider, encrypted OAuth tokens, account mapping |
| `accounting_sync_runs`, `accounting_sync_items` | sync history; items make re-syncs idempotent |
| `campaigns`, `campaign_recipients` | one-shot SMS/email campaigns: segment + lookback, delivery counts, per-recipient status |
| `push_config` (registry) | deployment-wide VAPID keypair; private key encrypted with `MASTER_KEK`, generated once when envs are unset |
| `push_subscriptions` | one row per browser: endpoint (unique per tenant), `p256dh`/`auth`, user agent, user FK |

Order lifecycle: `scheduled → in_progress → awaiting_parts → completed → invoiced`
(+ `cancelled` from any non-invoiced state). Invoices snapshot line items so
later edits to the order cannot mutate issued financial documents.

Accounting sync posts paid invoices as journals: the service builds debit (payment/undeposited
funds) and credit (income + tax) lines, posts to QBO `JournalEntry` or Xero `ManualJournal`, and
records each invoice in `accounting_sync_items` so re-runs skip what already posted; the provider is
fixed per deployment (`ACCOUNTING_PROVIDER=stub|quickbooks|xero`) and OAuth tokens are stored
AES-GCM-encrypted. A keyless journal CSV export works on any plan with `accounting_sync`.

Campaign audiences are computed from customers and service history at preview/send time (not
stored): `all`, `inactive` (no order within the lookback window, including never-ordered
customers), and `due_service` (last completed service older than the window). Sending writes one
`campaign_recipients` row and one `notifications` outbox row per reachable customer, so provider
failures are visible per recipient instead of failing the whole run.

Stock changes never write `parts.stock_qty` directly: the inventory service appends a
`stock_movements` row and updates the balance in one transaction, rejects negative stock (409), and
returns quantities when a linked line is removed or the order is cancelled. `parts` and
`stock_movements` are FORCE-RLS tenant tables; the `inventory` entitlement gates the API and UI.

Locations are branches inside one tenant: `locations` is a FORCE-RLS table with exactly one
default enforced by the service, `service_orders.location_id` is assigned from the payload or the
default on create (`ON DELETE SET NULL` so history survives), and delete is refused while orders
reference the row. Customers and vehicles are shared across branches; inventory and staff stay
tenant-wide. No entitlement gates locations.

Supplier search is served by two providers behind one interface: `stub` returns an in-code
catalog, `csv` reads `supplier_catalog_items` (FORCE RLS, cascade-deleted with the connection).
Search normalizes offers from every connection for the tenant; Import re-resolves the offer and
upserts `parts` by SKU, so cost/price/brand stay in sync while stock is owned by the inventory
ledger (new parts start at 0). Ordering stays at the supplier: the connection's `portal_url` is
returned per offer. Real distributor APIs (PartsTech/NexPart/WHI) are partner-gated, so adding one
later means a new provider branch, not a schema change. The `suppliers` entitlement gates
mutation and read.

Push notifications ride the deployment's own VAPID keypair (env `VAPID_*`, or auto-generated into
the `push_config` registry row on first use) and `push_subscriptions` (FORCE RLS) hold one row per
browser; `services/push.py` posts through `pywebpush` in a worker thread, prunes rows on 404/410,
and never raises into the request path. Triggers live in the booking and order services, so both
the public booking endpoint and staff order edits notify the same way. No entitlement gate: there
is no paid provider to meter.

## The 10 SaaS patterns → where they live

| Pattern | Implementation |
|---|---|
| Dynamic hybrid data isolation | RLS pool + `isolation_tier`/`region` hooks (`tenancy.py`, `db/session.py`) |
| Geo compliance routing | `tenants.region` + `REGION_DATABASE_URLS` resolution in `db/engine_map.py` |
| Self-serve provisioning | `/signup` availability check + auto-slug + atomic tenant bootstrap (`services/provisioning.py`) |
| Central identity & RBAC | JWT + refresh rotation, roles owner→viewer, `require_role()` |
| Localized billing | `services/billing/*` provider abstraction (stub/paddle/stripe), currency per tenant, MoR-ready |
| Noisy-neighbor throttling | Redis per-tenant windows by plan + per-IP login limit (`core/rate_limit.py`) |
| White-label / custom domains | tenant branding → runtime CSS vars; `tenant_domains` + Caddy on-demand TLS + `/tls/ask`; per-tenant email sender |
| BYOK encryption | envelope: master KEK wraps per-tenant DEK (`core/crypto.py`, `tenant_keys`) |
| Feature flags & entitlements | plan catalog → `features` JSONB; `require_feature()`; client reads `/me` |
| Sharded observability | `tenant_id` on every log/metric/audit row; per-tier sampling; OTLP hook |

## Frontend

- Next.js App Router; server components for data-light pages, SWR for live lists.
- Same-origin API through Caddy (`/api/*`) — refresh token is an httpOnly cookie,
  so no token lives in JS storage.
- Theming: CSS variables (`--brand-*`) set from tenant branding returned by
  `/api/v1/public/branding` — white-label without rebuild.
- PWA: installable, offline app shell, responsive layouts (sidebar → bottom nav),
  WCAG 2.2 AA practices (EAA legal requirement for EU sales).
- Locale-aware number/currency formatting via `Intl`.
