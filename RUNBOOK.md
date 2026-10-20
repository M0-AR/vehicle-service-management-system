# RUNBOOK — Vehicle Service Management SaaS

Operations guide for the Docker Compose deployment (`docker-compose.yml`).

## Start / stop / update

```bash
make up            # build + start everything
make logs          # tail logs
make down          # stop (volumes kept)
docker compose down -v   # full reset (DELETES DATA)
```

Update procedure:

```bash
git pull
docker compose build && docker compose up -d
docker compose exec backend alembic upgrade head
```

## Health & monitoring

| Check | Endpoint / command |
|-------|--------------------|
| Liveness  | `curl localhost/api/v1/livez` (via Caddy) or `:8000/api/v1/livez` |
| Readiness | `/api/v1/readyz` (checks DB; 503 when down) |
| Version   | `/api/v1/version` |
| Metrics   | `http://<backend>:8000/metrics` (Prometheus, per-tenant counters) or Caddy's `/metrics` when enabled |
| Container health | `docker compose ps` — every service has a healthcheck |

## Migrations & seed

```bash
docker compose exec backend alembic upgrade head     # migrate
docker compose exec backend alembic revision -m "..." --autogenerate
docker compose exec backend python -m app.seed       # idempotent demo data
```

## Backups

- **Postgres** (all tenants live in one database):
  `docker compose exec postgres pg_dump -U postgres vsms | gzip > backup-$(date +%F).sql.gz`
- Redis holds only throttling counters; losing them is safe (limits reset).
- Restore into a fresh volume with the same `pg_dump`/`psql` pair, then run
  `alembic upgrade head` to be sure the schema matches the app version.

## Secret rotation

| Secret | How |
|--------|-----|
| `JWT_SECRET` | Replace, `docker compose up -d backend`. All sessions invalidate (acceptable: refresh tokens fail closed). |
| `POSTGRES_PASSWORD` / `APP_DB_PASSWORD` | `ALTER ROLE ... PASSWORD '...'` inside postgres, update `.env`, recreate backend. |
| `MASTER_KEK_B64` | Rotate **carefully**: re-wrap every tenant's `byok_dek` with the new KEK before switching (see `docs/SECURITY.md`); there is no automated re-wrap script. |
| Provider keys (Paddle/Stripe) | Update `.env`, recreate backend; webhooks keep working since the URL is stable. |

## Custom domain onboarding (tenant-facing flow)

1. Tenant adds the domain in **Settings → Domains** (requires the
   `custom_domain` entitlement; Pro+).
2. The app shows a TXT record `_vsms-verify.<domain>` with a token.
3. Tenant publishes the TXT record, clicks **Verify** → backend resolves the
   TXT via DNS and marks the domain `verified`.
4. Caddy issues the certificate on first request using
   **on-demand TLS** gated by `/api/v1/tls/ask` (200 only for verified
   domains; 403 otherwise — issuance abuse blocked).

If issuance fails: check `docker compose logs caddy`, confirm the DNS TXT is
live (`dig +short TXT _vsms-verify.<domain>`), and that `ACME_EMAIL` is set.

## Billing provider switch

Default is `BILLING_PROVIDER=stub` (plan changes apply instantly, nothing is
charged — good for demos and tests).

For Paddle: set `BILLING_PROVIDER=paddle`, `PADDLE_API_KEY`,
`PADDLE_WEBHOOK_SECRET`, `PADDLE_ENVIRONMENT=sandbox|production`, then point
the Paddle webhook to `https://<platform>/api/v1/webhooks/billing/paddle`.
Stripe is equivalent (`/api/v1/webhooks/billing/stripe`, secret in
`STRIPE_WEBHOOK_SECRET`). Always re-test upgrades/downgrades in sandbox first.

## Accounting provider switch

Default is `ACCOUNTING_PROVIDER=stub` (keyless demo: connect, sync and CSV all work; journals get
synthetic ids). To use a real provider set `ACCOUNTING_PROVIDER=quickbooks` with
`QUICKBOOKS_CLIENT_ID`/`QUICKBOOKS_CLIENT_SECRET`/`QUICKBOOKS_ENVIRONMENT=sandbox|production`
(optional `QUICKBOOKS_REDIRECT_URI`), or `ACCOUNTING_PROVIDER=xero` with
`XERO_CLIENT_ID`/`XERO_CLIENT_SECRET` (optional `XERO_REDIRECT_URI`). Register the redirect URI
`<PUBLIC_APP_URL>/app/settings?tab=accounting` in the provider's app settings. Without credentials
the API returns 409 guidance and the UI disables Connect. Tokens are encrypted with `MASTER_KEK_B64`
— set it before connecting or the callback fails. Re-run a sync after switching providers; already
posted invoices are skipped only per provider, so reconnect and re-sync to backfill.

## SMS, uploads and public links

- **SMS** is off unless a Twilio-compatible provider is configured:
  `SMS_ACCOUNT_SID`, `SMS_AUTH_TOKEN`, `SMS_FROM_NUMBER` (optional
  `SMS_PROVIDER`/`SMS_API_BASE` for another REST-compatible gateway). Every
  message is recorded in the tenant outbox; while unconfigured it shows as
  **Skipped** ("SMS provider is not configured") and Settings → Notifications
  returns a 409 with the same guidance. Test after configuring with the
  Settings → Notifications form.
- **Email** is off unless SMTP is configured: `SMTP_HOST` + `SMTP_FROM` (plus `SMTP_PORT`,
  optional `SMTP_USERNAME`/`SMTP_PASSWORD`, `SMTP_SECURITY=starttls|ssl|none`). Messages are
  plain-text through the server's relay; with no config they record **Skipped** and the test
  endpoint returns 409 naming the envs. `SMTP_FROM` may be `Shop <no-reply@shop.example>`.
  Settings → Notifications tests either channel.
- **Marketing campaigns** reuse this outbox. With no provider configured a send still completes
  and marks each recipient **Skipped**, so the campaign is recorded honestly with `0 sent`; the
  UI toast and the campaign detail explain why. Email recipients go through SMTP when it is
  configured.
- **Web Push** works without configuration: the backend generates a VAPID keypair once and stores
  it (private key encrypted with `MASTER_KEK_B64`) in the `push_config` registry row. Set
  `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` (PEM) / `VAPID_SUBJECT` explicitly to pin keys across
  environments or rotate them. Push is delivered by `pywebpush` in the image; subscriptions are
  per browser and pruned automatically when the push service answers 404/410. Staff enable it in
  Settings → Notifications and can send a test there. Browser permission cannot be requested
  programmatically — if it is blocked, the user must reset it in the browser's site settings.
- **Inspection photos** live on the `uploads` volume (`STORAGE_DIR=/data/uploads`,
  8 MB per file, JPEG/PNG/WebP only). Back it up with the database; the backend
  container creates it with the right ownership (`uid 1001`).
- **Public links** (status, estimate, review) and SMS URLs use
  `PUBLIC_APP_URL` as the base — set it to the customer-facing origin
  (e.g. `https://shop.example.com`) or review SMS links will be relative.
- **Dev port override**: `docker-compose.override.yml` publishes Caddy on
  `:8090`/`:8453` so the production `:80`/`:443` stay free; delete it when this
  host is the real edge.

## Supplier catalogs

Supplier integration is provider-based and keyless by default. `stub` connections serve a small
in-code demo catalog; `csv` connections search the tenant's uploaded price list. CSV header:
`sku,description` required, optional `brand,cost,price,stock`; uploads are capped at 2 MB and
5,000 rows, invalid rows are skipped and counted, and rows upsert on SKU. Import into inventory
matches parts by exact SKU (creates at stock 0, else updates brand/supplier/cost/price). Each
connection may carry a portal URL; ordering happens at the supplier because PO transmission is
not implemented (PartsTech/NexPart/WHI require partner onboarding). No environment variables are
needed; `suppliers` is a pro/enterprise entitlement added by migration `0009`.

## Security headers

Caddy applies the baseline on every site (and Next.js repeats it for direct
`next start` use): CSP (`default-src 'self'`, inline scripts/styles for Next,
`img-src ... https:` for tenant logos), `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Permissions-Policy: camera=(), microphone=(), geolocation=()`. HSTS
(`max-age=31536000`) is added only on TLS-enabled site blocks. Keep the two CSP
definitions in sync when adding third-party origins.

## Rate limiting

Per-plan requests/min live in `.env` (`RATE_LIMIT_FREE|PRO|ENTERPRISE`) plus
`LOGIN_RATE_PER_MINUTE` for the tenant+IP login bucket. Counters are Redis
fixed-window keys `rl:*`. To disable (e.g. local load testing) set
`RATE_LIMIT_ENABLED=false`. A Redis outage fails **open** (requests pass) by
design; the readiness probe does not depend on Redis.

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `All 401` after deploy | `JWT_SECRET` changed or missing in container env — check `docker compose exec backend env \| grep JWT`. |
| `404` on a valid resource | Wrong tenant: the `X-Tenant-Slug` header / Host subdomain doesn't match the record's tenant (RLS hides cross-tenant rows as 404, not 403, on purpose). |
| `402` on branding/API keys/domains | Feature not in the tenant's plan — upgrade plan or check `plan.features` merge with `tenant_settings` overrides. |
| `429` during tests | Throttling; set `RATE_LIMIT_ENABLED=false` and recreate backend. |
| Frontend `502` on `/api/*` | Backend not healthy or `BACKEND_INTERNAL_URL` wrong (build-time for rewrites; default `http://backend:8000`). |
| Caddy keeps requesting certs | `/api/v1/tls/ask` down or domain not verified — fix the backend first; Caddy will retry on demand. |
| `readyz` 503, `livez` 200 | DB unreachable — check postgres health and `DATABASE_URL`/role password. |

## Backend tests

```bash
cd backend
TEST_ADMIN_DSN=postgresql://postgres:postgres@localhost:5432/postgres python -m pytest -q
```

The suite needs a superuser DSN to create/drop the throwaway test database
(it validates RLS by attempting cross-tenant reads). Without Docker, point
`TEST_ADMIN_DSN` at any disposable Postgres.
