<p align="center">
  <img src="assets/brand/banner.png" alt="Vehicle Service Manager — run your shop, not your paperwork" width="100%">
</p>

<h1 align="center">Vehicle Service Manager</h1>

<p align="center">
  <strong>The calm operating system for independent auto shops.</strong><br>
  Vehicles, service orders, photo inspections, estimates, invoices, inventory and marketing —<br>
  one multi-tenant workspace, isolated per business, ready to white-label.
</p>

<p align="center">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-16-12251F?style=flat-square&logo=nextdotjs&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Python-0E7C66?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-RLS-4169E1?style=flat-square&logo=postgresql&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white">
  <img alt="PWA" src="https://img.shields.io/badge/PWA-installable-5A0FC8?style=flat-square">
</p>

<p align="center">
  <a href="#quick-start"><strong>Quick start</strong></a> ·
  <a href="preview.html"><strong>Interactive preview &amp; quiz</strong></a> ·
  <a href="#beginner-guide"><strong>Beginner guide</strong></a> ·
  <a href="#plans"><strong>Plans</strong></a>
</p>

<p align="center">
  <img src="assets/gif/tour.gif" alt="A tour of the dashboard, service orders, photo inspections, estimates, booking and billing" width="900">
</p>

---

## What this is

Most shop software is either a spreadsheet with a login screen or an enterprise
suite that needs a consultant to configure. **Vehicle Service Manager** is the
middle path: a complete, production-shaped workspace that an independent garage
can run on day one, and a software team can white-label, extend and host for many
shops at once.

One codebase serves many workspaces. Each workspace gets its own users, customers,
vehicles, orders, money and branding — separated in PostgreSQL by row-level
security, not by hopeful `WHERE tenant_id = ...` clauses in application code.

It covers the whole day: a customer books online, the front desk turns the request
into a service order, a mechanic records a photo inspection, the advisor sends an
estimate, the customer approves it from their phone, the work is completed, an
invoice is paid by card, a review request goes out, and every step is written to
an audit trail.

## Why it matters

The independent repair shop is the default way the world keeps cars on the road,
yet the tools serving it are fragmented and often dated.

| Signal | What it means |
|---|---|
| **$129B** US auto repair market | A large, durable category — not a niche experiment. |
| **227,418** active repair locations | Enough independent operators to support a multi-tenant product. |
| **~870,000** mechanics | Staff adoption and fast onboarding matter more than feature count. |
| **92%** independent shops | The top ten banners hold only 5–8% of locations. |
| **12.6 years** average vehicle age | More maintenance, more inspections, longer customer relationships. |
| **$586** average invoice | Small gains in approvals and repeat visits compound quickly. |
| **<35%** on modern cloud tools | The upgrade cycle is still early; trust and simplicity win. |

Sources: [Orbital — Automotive Repair Industry Statistics](https://www.withorbital.com/data/automotive-repair-industry-statistics)
(updated June 2026). The cloud-software figure is an industry estimate, not a
census; treat it as directional.

## Who it is for

| Operator | What they get |
|---|---|
| **Independent garages** | One place for the front desk, the bay and the books — without an IT department. |
| **Tire, brake and quick-lube shops** | Fast check-in, photo inspections and estimates that customers approve on their phone. |
| **EV and hybrid specialists** | Vehicle history, custom inspection templates and line-item work, without a separate DMS. |
| **Multi-location groups** | Branch-aware orders, staff roles, shared catalogs and a group-level audit trail. |
| **Fleet and maintenance teams** | Repeatable service orders, status links and exportable records. |
| **Software partners** | A white-label, multi-tenant foundation with plans, entitlements and custom domains already wired. |

## Everything inside

### Front desk and scheduling

- **Online booking** — a public, tenant-branded page with open slots; requests land
  in the workspace as booking requests, ready to convert into orders.
- **Service orders** — scheduled, in progress, awaiting parts, completed, invoiced
  or cancelled; priority, technician, location, odometer and a full timeline.
- **Customers and vehicles** — contact history, plates, VIN, make/model/year and
  service history in one profile.
- **VIN lookup** — decode a VIN through the NHTSA vPIC service to prefill vehicle
  details and reduce typing mistakes.
- **Tokenized status links** — customers follow progress without an account, and
  without seeing anyone else's data.

### Workshop

- **Digital vehicle inspections (DVI)** — inspection items with condition status,
  notes and photos; completed inspections are locked for integrity.
- **Photo evidence** — upload condition photos that appear on the customer status
  page, so “your brakes are at 3 mm” comes with a picture.
- **Inventory and parts** — parts catalog, stock movements, low-stock signals and
  parts attached to order line items.
- **Supplier catalogs** — supplier connections, CSV price-list import, search and
  one-click import into your own parts catalog.

### Money

- **Estimates** — labour and parts line items, tax, notes, and a public approval
  page with a secure token.
- **Invoices** — draft, sent, paid, overdue and void states; due dates, tax,
  partial context and a printable layout.
- **Card payments** — Stripe checkout links for invoice payment when provider keys
  are configured; the default billing provider is a safe stub.
- **Accounting sync** — QuickBooks and Xero adapters plus a journal CSV export for
  the tools that already own the books.

### Growth

- **Review requests** — ask at the right moment with a secure link; capture a
  rating and comment without another login.
- **Marketing campaigns** — customer segments, message preview, recipient counts
  and an SMS/email outbox with explicit sent, skipped and failed states.
- **Reminders** — service and booking reminders through the same outbox, so
  nothing silently disappears when a provider is not configured.

### Platform

- **Multi-tenancy** — header, subdomain or custom domain resolves the workspace;
  PostgreSQL row-level security enforces the boundary.
- **Roles** — owner, manager, mechanic and viewer, with tenant-aware permissions.
- **Plan entitlements** — features are gated and enforced on the server, not just
  hidden in the UI.
- **White-label branding** — logo, colours and support email per workspace.
- **Custom domains** — TXT verification and on-demand TLS through the edge.
- **Audit log** — who changed what, when, and from where.
- **PWA and Web Push** — installable on a phone; per-device staff subscriptions.
- **API access** — tenant-scoped API keys and a documented FastAPI surface.
- **BYOK** — envelope-encrypted bring-your-own provider keys on Enterprise.
- **Observability** — health endpoints, Prometheus metrics and structured logs.

## A look around

<table>
<tr>
<td width="50%"><img src="assets/screenshots/dashboard.png" alt="Dashboard with revenue, money owed, order status and upcoming work"><br><sub><strong>Dashboard</strong> — the day at a glance.</sub></td>
<td width="50%"><img src="assets/screenshots/orders.png" alt="Service order list with statuses, priorities and totals"><br><sub><strong>Service orders</strong> — every job, one board.</sub></td>
</tr>
<tr>
<td width="50%"><img src="assets/screenshots/dvi-order.png" alt="Completed service order with line items and a photo inspection"><br><sub><strong>One job, full context</strong> — work, parts and photo evidence.</sub></td>
<td width="50%"><img src="assets/screenshots/invoices.png" alt="Invoice list with paid and sent states"><br><sub><strong>Billing</strong> — send, track and mark paid.</sub></td>
</tr>
</table>

### The customer journey

<p align="center">
  <img src="assets/gif/customer-journey.gif" alt="Customer books online, approves an estimate, leaves a review and tracks status" width="820">
</p>

Every public step is tokenized and tenant-scoped: booking, estimate approval,
review and live status. No customer account, no exposed internal IDs, no shared
login.

<table>
<tr>
<td width="50%"><img src="assets/screenshots/booking.png" alt="Public booking page with availability and vehicle details"><br><sub><strong>Book</strong> — availability and vehicle details in one pass.</sub></td>
<td width="50%"><img src="assets/screenshots/estimate-public.png" alt="Public estimate approval page"><br><sub><strong>Approve</strong> — an itemised estimate on any phone.</sub></td>
</tr>
<tr>
<td width="50%"><img src="assets/screenshots/status.png" alt="Customer status page with inspection photo"><br><sub><strong>Track</strong> — live progress and inspection photos.</sub></td>
<td width="50%"><img src="assets/screenshots/review.png" alt="Public review page"><br><sub><strong>Review</strong> — a five-star ask at the right moment.</sub></td>
</tr>
</table>

## Quick start

Requirements: Docker with Compose v2.

```bash
cp .env.example .env          # edit the change-me values
make up                       # build and start the stack
make migrate                  # migrations + idempotent demo seed
open http://localhost         # or http://localhost:8090 if ports 80/443 are taken
```

The seed creates two ready-to-use workspaces:

| Workspace | Slug | Login | Password | Plan |
|---|---|---|---|---|
| Downtown Auto Care | `demo` | `owner@demo.example` | `demo-password-123` | Pro |
| Quick Lube Co. | `quicklube` | `owner@quicklube.example` | `demo-password-123` | Free |

Sign in at `http://localhost/login?demo=1`. The query parameter pre-fills the
credentials — it does not bypass authentication.

> **Local TLS:** with `PLATFORM_BASE_DOMAIN=localhost`, Caddy serves plain HTTP on
> `localhost` and `*.localhost`. In production, set `PLATFORM_BASE_DOMAIN` and
> `ACME_EMAIL` and the edge issues certificates automatically.
>
> If ports 80/443 are busy, the checked-in `docker-compose.override.yml` publishes
> Caddy on `:8090`/`:8453`; open `http://localhost:8090`.

### First five minutes in the product

1. Open **Service orders → New order**, pick a customer and vehicle, add a labour
   and a parts line.
2. Open the order and click **Start inspection**; add an item with a photo and mark
   it **Attention**.
3. Click **Create invoice**, then **Share status link** and open the link in a
   private window.
4. Go to **Estimates → New estimate**, add lines, send it, and approve it through
   the public link.
5. Open **Marketing**, build a segment and preview a campaign without sending it.

## Architecture

```mermaid
flowchart LR
    B[Browser / PWA] -->|HTTPS| C[Caddy edge<br/>TLS · routing · headers]
    C -->|/api/*| A[FastAPI<br/>auth · tenancy · entitlements]
    C -->|/*| N[Next.js 16<br/>App Router]
    A -->|tenant-scoped session| P[(PostgreSQL<br/>row-level security)]
    A --> R[(Redis<br/>throttling · rate limits)]
    A --> O[Outbox<br/>email · SMS]
    A --> S[Stripe · suppliers · accounting]
```

- **Tenant resolution** happens at the edge and in the API: `X-Tenant-Slug`, the
  subdomain, or a verified custom domain. The resolved tenant becomes a
  transaction-local PostgreSQL setting.
- **RLS is fail-closed.** A request without a tenant context sees nothing, not
  everything.
- **Entitlements are checked server-side** for plan-gated routes, so hiding a
  button is never the security boundary.
- **Public links are random tokens**, scoped to one entity and revocable.

More detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/SECURITY.md`](docs/SECURITY.md), [`docs/RESEARCH.md`](docs/RESEARCH.md).
Operations: [`RUNBOOK.md`](RUNBOOK.md).

## Security and isolation

- PostgreSQL row-level security on tenant-owned tables, with a fail-closed GUC.
- JWT access and refresh tokens; tenant-aware login; role checks on every route.
- Plan entitlements enforced in the API, not only in the interface.
- Tokenized, revocable public links for estimates, reviews and status pages.
- Audit entries for security-relevant and money-relevant actions.
- Strict security headers at the edge (CSP, frame ancestors, referrer policy,
  permissions policy, HSTS in production).
- Secrets never shipped to the browser; provider keys encrypted at rest with
  envelope encryption for BYOK workspaces.
- Per-tenant throttling to contain noisy neighbours.

This is a strong foundation, not a certification. See **Honest scope** below.

## Plans

The demo seed ships with three plans. Limits and features are enforced by the
server and can be edited in the plan records.

| | **Free** | **Pro** | **Enterprise** |
|---|---|---|---|
| Price | $0 | $29 / month | $99 / month |
| Users | 3 | 20 | Unlimited |
| Vehicles | 50 | 1,000 | Unlimited |
| Orders / month | 100 | 5,000 | Unlimited |
| Online booking, estimates, invoices | ✓ | ✓ | ✓ |
| Photo inspections (DVI) | — | ✓ | ✓ |
| Inventory, suppliers, marketing | — | ✓ | ✓ |
| Review requests, SMS, online payments | — | ✓ | ✓ |
| Accounting sync, white-label, custom domain | — | ✓ | ✓ |
| Audit log, API access | — | ✓ | ✓ |
| BYOK (bring your own keys) | — | — | ✓ |

Prices and limits reflect the checked-in seed; review them before a commercial
launch.

<a id="beginner-guide"></a>

## 🌱 Beginner guide — read this and you are a professional

**Let's work this out in a step-by-step way to be sure we have the right answer.**

You do not need to know the stack to understand the product. Start with the words.

| Word | Plain English |
|---|---|
| **Workspace / tenant** | One shop's account. Its data is invisible to every other shop. |
| **RLS** | A database rule that filters rows by workspace, even if application code forgets to. |
| **Service order** | The job: a vehicle, a complaint, line items and a lifecycle from scheduled to invoiced. |
| **DVI** | Digital Vehicle Inspection: a checklist with condition notes and photos. |
| **Estimate** | What you propose and what it will cost. It is not a bill. |
| **Invoice** | The request for payment after work is agreed or done. |
| **Entitlement** | A feature the workspace's plan allows, checked on the server. |
| **Tokenized link** | A long random URL that grants access to exactly one estimate, review or status page. |
| **Outbox** | A record of every message the system tried to send, including skipped and failed ones. |

### The eight-step mental model

1. **A workspace is created.** A tenant row, an owner, a plan and branding are
   written. Every later row carries that tenant ID.
2. **A customer and vehicle are added.** The vehicle belongs to the customer and
   the workspace; the plate is unique inside the workspace.
3. **A booking or order is created.** A booking is an inbound request; an order is
   the operational job with a status and a timeline.
4. **The bay does the work.** Line items capture labour and parts; inventory can
   move when parts are consumed.
5. **An inspection records condition.** Items and photos become evidence, and the
   customer status link can show them.
6. **An estimate asks for a decision.** A public token lets the customer approve
   without an account. Approved work can become an order.
7. **An invoice asks for money.** Statuses track draft, sent, paid, overdue and
   void; Stripe can collect the card payment.
8. **Retention and governance close the loop.** A review request goes out, a
   campaign can bring the customer back, and the audit log records who did what.

### Why the design choices matter

- **Why RLS instead of only `WHERE tenant_id`?** One forgotten filter in one query
  is a cross-tenant data leak. RLS makes the database refuse the row.
- **Why server-side entitlements?** A hidden button is a UX choice; an API check is
  a security boundary.
- **Why tokenized public links?** Customers should not need a password to approve
  an estimate, and a link should reveal one record, not a workspace.
- **Why an outbox?** “We sent it” must be provable. Sent, skipped and failed are
  different outcomes, especially when SMS is optional.
- **Why lock completed inspections?** An inspection is evidence. Editing it after
  completion destroys trust.

You will know more than most interview candidates. If you want the fast version,
open the **[interactive preview](preview.html)** — it has the product tour, a
plain-English learning path, an economics calculator and a quiz that explains every
answer.

## Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://app_user:app_password@localhost:5432/vsms
export JWT_SECRET=dev-only-secret
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`. Health: `/api/v1/livez`, `/api/v1/readyz`,
`/api/v1/version`.

### Frontend

```bash
cd frontend
npm ci
npm run dev        # http://localhost:3000, /api/* proxied to :8000
```

### Tests and checks

```bash
cd backend && python -m pytest -q
cd frontend && npm run typecheck && npm run build
```

The backend suite creates a throwaway PostgreSQL instance through Docker and
covers authentication, tenancy, RLS, billing, inventory, suppliers, marketing,
accounting, inspections and the email outbox.

## Configuration

Copy `.env.example` and adjust at least:

| Variable | Why it matters |
|---|---|
| `DATABASE_URL` | PostgreSQL connection used by the API and migrations. |
| `JWT_SECRET` | Signs access and refresh tokens. Use a long random value. |
| `PLATFORM_BASE_DOMAIN` | Root domain for workspace subdomains and custom-domain routing. |
| `ACME_EMAIL` | Contact address for automatic TLS certificates. |
| `REDIS_URL` | Throttling and rate-limit backend. |
| `SMTP_*` | Invites, invoices and reminders; without it, email is recorded as skipped. |
| `TWILIO_*` | Optional SMS delivery; without it, SMS is recorded as skipped. |
| `STRIPE_*` | Invoice card payments and subscription billing when configured. |
| `VAPID_*` | Web Push keys for staff notifications. |

Provider integrations are adapters: supplier catalogs, QuickBooks/Xero and push
need real credentials before they leave the safe stub path.

## Project layout

```text
backend/
  app/api/routers/      auth, orders, inspections, estimates, invoices,
                        inventory, suppliers, campaigns, accounting, public
  app/core/             tenancy, RLS session, entitlements, crypto, audit
  app/models/           SQLAlchemy models for every tenant-owned table
  app/services/         billing, notifications, suppliers, accounting, push
  migrations/           Alembic history
  tests/                pytest suite
frontend/
  src/app/              marketing site, auth, workspace, public token pages
  src/components/       app shell, tables, settings panels, public views
  src/lib/              API client, branding, auth, push
infra/
  caddy/                edge routing, TLS, security headers
  postgres/init/        database roles and bootstrap SQL
assets/
  brand/                banner and social preview
  gif/                  product tour and customer journey
  screenshots/          the images used in this README
  video/                MP4 product tour
docs/                   architecture, security, research, roadmap
```

## Preview site and GitHub Pages

The repository includes a standalone, dependency-free marketing and learning page:

- `preview.html` — product tour, feature atlas, economics calculator, learning
  path, FAQ and a scored quiz.
- `index.html` — a zero-JavaScript redirect so the root of a static host opens the
  preview.

To publish with GitHub Pages:

1. Push the repository to GitHub.
2. Open **Settings → Pages**.
3. Choose **Deploy from a branch**, select your default branch and the repository
   root (`/`).
4. Save. The preview will be served at `https://<owner>.github.io/<repo>/`.

All asset paths are relative, so the page works from a project subpath as well as
a custom domain. Upload `assets/brand/banner.png` as the repository social preview
(1280×640) in **Settings → General → Social preview**.

## Honest scope

This is a production-grade foundation, not a certified product:

- **Not** SOC 2 or ISO 27001 certified, and not penetration-tested.
- **Not** load-tested beyond basic smoke runs; Redis throttling is fixed-window,
  not a distributed token bucket under extreme fan-in.
- Billing defaults to a **stub provider** (no card charged). Paddle/Stripe are
  wired but sandbox-only until live keys and webhooks are tested.
- SMS is opt-in: without Twilio-compatible credentials, messages are recorded in
  the outbox as **Skipped** and nothing leaves the server.
- Email requires SMTP configuration. Without it, messages are recorded as skipped
  rather than silently lost.
- Supplier, accounting and push integrations are adapters; they need real
  credentials and provider-side testing before production use.
- Single-region by default; `REGION_DATABASE_URLS` routes connections, but there
  is no cross-region failover.
- No license file is included yet. Add one before distributing or accepting
  outside contributions.

## Contributing

Small, focused pull requests are welcome. Keep the guardrails intact:

- Add or update tests for behaviour changes; the backend suite must stay green.
- Record security-relevant actions in the audit log.
- Enforce plan gates on the server, not only in the interface.
- Keep public pages tokenized, tenant-scoped and accessible by keyboard.
- Update this README, `RUNBOOK.md` and the relevant `docs/` page when behaviour
  changes.

## Roadmap

- Deeper supplier ordering (purchase orders, receipts, backorders).
- Two-way accounting sync with reconciliation reports.
- Technician scheduling board and bay capacity planning.
- Customer self-scheduling changes and cancellation windows.
- More inspection templates and vehicle-class presets.
- Usage-based plan reporting and dunning.

---

<p align="center">
  <strong>Built for the people who keep the world moving.</strong><br>
  <sub>If this saves your front desk one hour a day, it is already doing its job.</sub>
</p>
