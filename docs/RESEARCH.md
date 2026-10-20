# RESEARCH — Vehicle Service Management SaaS

Every architectural decision below was **verified online before any code was
written** (rule: no file gets enhanced by hand without verification). Sources
were read directly where marked ✅. All retrieved **2026-10-18**.

## 1. Multi-tenancy model

**Decision: shared-schema pool + PostgreSQL Row-Level Security (RLS), with a
per-tenant `silo` escape hatch and region-routing hook (hybrid isolation).**

Verified against primary docs:

- ✅ PostgreSQL docs — Row Security Policies (https://www.postgresql.org/docs/current/ddl-rowsecurity.html):
  - Tables are **default-deny** once RLS is enabled and no policy matches.
  - **Superusers and `BYPASSRLS` roles bypass RLS**; owners bypass by default →
    use `ALTER TABLE ... FORCE ROW LEVEL SECURITY` so the migration owner is subject too.
  - `USING` controls visibility, `WITH CHECK` controls writability — both needed.
  - Referential integrity checks bypass RLS → keep FKs within tenant rows.
  - `row_security = off` turns silent filtering into an **error** (use for dumps/jobs).
- ✅ Nile Engineering — "Shipping multi-tenant SaaS using Postgres Row-Level Security"
  (254 HN points, https://www.thenile.dev/blog/multi-tenant-rls):
  - `WHERE tenant_id = ...` fails *open* (forgot the filter = leak); RLS **fails closed**.
  - Policies attach to **tables, not queries** → defined once, enforced everywhere.
  - Dedicated non-owner role (`app_user`, NOSUPERUSER, NOBYPASSRLS).
  - Recursive admin checks → `SECURITY DEFINER` functions with hardened `search_path`.
  - Request-scoped context must be **reset/transaction-scoped** (their bug: thread-local leaked).
- OWASP Multi-Tenant Security Cheat Sheet (https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html)
  + AWS SaaS Lens: tenant context must come from **verified identity**, never client headers alone.
- PgBouncer/pooler note (https://stackoverflow.com/questions/80003232): use
  **transaction-scoped** `set_config('app.current_tenant', :t, true)` — third arg
  `true` = `SET LOCAL`; pool-safe. Session-scoped `SET` leaks across pooled requests.

Implementation here: `app/core/tenancy.py` + migration `0001` (FORCE RLS on every
business table, policy `tenant_id = current_setting('app.current_tenant')::uuid`
via fail-closed `NULLIF` helper) + tests `test_rls_isolation.py` (negative paths).

## 2. Application stack

- **Backend: FastAPI + SQLAlchemy 2 (async) + asyncpg + Alembic + PyJWT.**
  (FastAPI typed-API conventions: https://fastapi.tiangolo.com/tutorial/sql-databases/;
  PyJWT over python-jose — CVE history.)
- **Frontend: Next.js 16 (App Router) + React 19 + TypeScript + Tailwind CSS v4**
  (https://tailwindcss.com/docs/theme — CSS-first tokens, runtime theming via CSS variables).
- **UI kit: shadcn/ui conventions on Radix primitives** (https://ui.shadcn.com/docs) —
  accessible primitives (focus management, ARIA) which we need for WCAG anyway.
- Verified against the workspace's prior SaaS build (`cab-booking-saas`) which had
  independently reached the same stack; patterns are reused, not reinvented.

## 3. Custom domains, subdomains, TLS

- **Pattern: subdomain per tenant (`<slug>.platform.tld`) + verified custom domains.**
  Validated against Twenty CRM (open source, production multi-tenant; source checked
  via gitmcp, 2026-10-18): their codebase has a dedicated `subdomain-manager` module
  (availability DTO, validation utils, random-slug generator), a
  `get-subdomain-and-custom-domain-from-hostname.util`, shared subdomain regex
  constants, settings/domains admin UI, and per-tenant email sender domains. We
  mirror this structure.
- **TLS: Caddy on-demand certificates + `ask` endpoint**
  (✅ read: https://www.bigiron.cc/guides/caddy-advanced-on-demand-tls-and-dynamic-config-with-the-admin-api):
  - `on_demand_tls { ask http://backend/api/v1/tls/ask }` — Caddy asks before issuing;
    2xx = issue, anything else = refuse. Rate limiting via `interval`/`burst`.
  - Keep Caddy admin API off the network (default localhost bind).
  - Custom domains resolve tenant in middleware from `Host` (never trusted for data
    access — only tenant *resolution*: auth JWT remains the authority).

## 4. Billing (localized, global sales)

- **Decision: provider-agnostic `BillingProvider` abstraction; MoR-first.**
  Selling globally means VAT/sales-tax; Merchant-of-Record providers (Paddle,
  Lemon Squeezy, Stripe Managed Payments) handle tax remittance so the vendor
  doesn't have to register in every jurisdiction. (Community/industry comparison
  retrieved via agent-reach search, 2026-10-18.)
- Implementation: `services/billing/` — `base.py` (protocol), `stub.py` (dev,
  works keyless), `paddle.py` + `stripe.py` skeletons behind env keys; webhook
  endpoint applies plan changes to tenant entitlements. Billing is the source of
  truth for plan → entitlements are read from DB, never from the client.

## 5. Feature entitlements vs release flags

- Verified distinction (Unleash / GrowthBook / OpenFeature docs):
  **entitlements = "did they pay for it"** (per-tenant DB, server-enforced) vs
  **release flags = "is it ready"** (deploy-time). Never gate only client-side.
- Implementation: `tenant_settings.features` JSONB + `plan` column + plan catalog;
  backend `require_feature()` dependency; frontend hides what `/me` doesn't grant.

## 6. Noisy-neighbor protection

- Microsoft Azure antipatterns — Noisy Neighbor
  (https://learn.microsoft.com/azure/architecture/antipatterns/noisy-neighbor)
  + AWS SaaS Lens isolation guidance: per-tenant throttling must be *fair*, not
  global. Implementation: Redis fixed-window per **tenant** (limit by plan) in
  `core/rate_limit.py`; login additionally throttled per IP. Fail-open with a
  loud log when Redis is down (availability bias, documented in SECURITY.md).

## 7. Observability (tenant-aware)

- OpenTelemetry multi-tenant guidance (https://opentelemetry.io/blog/2026/otel-native-by-design/;
  plus an academic reference framework on tenant-aware enrichment pipelines,
  OpenAlex 2026): every signal carries `tenant.id`; sampling can be per-tier;
  silo-tier tenants get a dedicated collector.
- Implementation: structured JSON logs with `tenant_id`/`user_id`/`request_id` in
  every request (`core/observability.py`), `X-Request-ID` propagation,
  Prometheus `/metrics` (bounded labels), OTLP hook via env when otel extras are
  installed. Audit log in DB for business-critical events.

## 8. Mobile strategy

- ✅ PWA-first (Next.js official PWA guide https://nextjs.org/docs/app/guides/progressive-web-apps;
  2026 comparisons: installable, offline-tolerant, no store gatekeeping; native
  (Expo) only if background GPS is ever needed — the API stays ready for it).
- Implementation: `manifest.webmanifest`, service worker with app-shell strategy,
  responsive layout with mobile navigation, touch targets ≥44px.

## 9. Accessibility is legal (EU sales)

- ✅ European Accessibility Act (Directive (EU) 2019/882) — **applies since
  28 June 2025**; standard is **EN 301 549 → WCAG 2.2 AA**; 2026 enforcement is
  real (French court: Carrefour €500/day until compliant; Spain: Vueling €90k;
  German Abmahnungen under BFSG). Sources: brimode.com WCAG 2.2 checklist
  (2026-09), accessscan.app SaaS guide, allaccessible.org.
- Implementation: semantic HTML, keyboard operability, visible focus, skip link,
  labels/roles from Radix primitives, 4.5:1 contrast tokens, `prefers-reduced-motion`
  support, accessible forms with error messaging. `lang` attributes and per-locale
  formatting hooks (Intl) prepared for i18n.

## 10. Deployment

- Root `docker-compose.yml`: postgres, redis, backend, frontend, caddy.
  Private `backend` network (`internal: true`) — DB/redis never publish ports;
  only the proxy is exposed. `healthcheck` + `depends_on: service_healthy` +
  `start_period` on every service (Docker docs best practice). Any cloud: one
  VM + DNS, or map each container to the provider's container service.
- Seeds: demo data generated synthetically (license-free). Kaggle has suitable
  real datasets for optional enrichment — e.g. `neerugattivikram/vehicle-service-and-repair-dataset-for-analysis`,
  `navins7/vehicle-maintenance-record`, `chavindudulaj/vehicle-maintenance-data`
  (cataloged 2026-10-18; not bundled).

## Source index (retrieved 2026-10-18)

| # | Source | Used for |
|---|--------|----------|
| 1 | https://www.postgresql.org/docs/current/ddl-rowsecurity.html | RLS semantics ✅ |
| 2 | https://www.thenile.dev/blog/multi-tenant-rls | RLS production gotchas ✅ |
| 3 | https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html | Tenant isolation security |
| 4 | https://fastapi.tiangolo.com/tutorial/sql-databases/ | FastAPI DB pattern |
| 5 | https://nextjs.org/docs/app/guides/progressive-web-apps | PWA strategy |
| 6 | https://tailwindcss.com/docs/theme | Tailwind v4 tokens |
| 7 | https://ui.shadcn.com/docs | Component/theming conventions |
| 8 | https://learn.microsoft.com/azure/architecture/antipatterns/noisy-neighbor | Per-tenant throttling |
| 9 | https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/noisy-neighbor.html | SaaS isolation |
| 10 | https://aws.amazon.com/blogs/apn/tenant-onboarding-best-practices-in-saas-with-the-aws-well-architected-saas-lens/ | Self-serve provisioning |
| 11 | https://stackoverflow.com/questions/80003232 | PgBouncer RLS leak |
| 12 | https://www.bigiron.cc/guides/caddy-advanced-on-demand-tls-and-dynamic-config-with-the-admin-api | On-demand TLS + ask ✅ |
| 13 | https://github.com/twentyhq/twenty (code, via gitmcp) | Subdomain/custom-domain module structure ✅ |
| 14 | https://opentelemetry.io/blog/2026/otel-native-by-design/ | Multi-tenant observability |
| 15 | https://www.brimode.com/insights/european-accessibility-act-wcag-2-2-checklist | EAA / WCAG 2.2 AA (legal) |
| 16 | https://accessscan.app/guides/eaa-compliance-for-saas | EAA scope for SaaS |
| 17 | https://www.mironsoft.de/en/blog/tailwind-white-label-theming-without-rebuild-runtime-variables | Runtime white-label theming |
| 18 | https://northflank.com/blog/multi-tenant-saas-platform-deployment | Deployment 2026 |
| 19 | https://openfeature.dev / unleash / growthbook docs | Entitlements vs flags |
| 20 | https://progressier.com/pwa-vs-native-app-comparison-table | PWA vs native 2026 |
