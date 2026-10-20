# SECURITY — Vehicle Service Management System

## Tenant isolation (the core guarantee)

- **RLS on every business table**, `FORCE ROW LEVEL SECURITY`, policies with both
  `USING` and `WITH CHECK`. Runtime role `app_user` is NOSUPERUSER, NOBYPASSRLS,
  non-owner — it *cannot* bypass policies.
- Tenant context is set with **transaction-scoped** `set_config(..., true)` so a
  pooled connection can never carry tenant context between requests
  (documented production failure mode; see docs/RESEARCH.md §1).
- The `tenant` claim in the JWT is authoritative; host headers only *resolve*
  which tenant a login/signup form refers to.
- Fail-closed test suite (`backend/tests/test_rls_isolation.py`) asserts, as
  `app_user`: tenant B sees zero rows while tenant A's context is unset; forged
  cross-tenant writes raise; `row_security = off` errors instead of silently
  returning everything.

## Authentication & sessions

- Argon2id (bcrypt-compatible fallback) password hashing; no password material in logs.
- Access tokens: JWT HS256, `sub`/`tenant`/`role`, 20 min TTL. Refresh tokens:
  48-byte random, **hashed at rest**, rotated on every use, revocable.
- Refresh token delivered as `httpOnly; Secure; SameSite=Lax` cookie scoped to
  `/api/v1/auth` (same-origin via the Caddy reverse proxy), so XSS cannot read it.
- Login throttled per IP and per tenant (Redis); uniform error messages (no
  account enumeration). Availability check endpoints are deliberately neutral.

## White-label / custom domains

- Custom-domain TLS is only issued for domains present in `tenant_domains`:
  Caddy's `ask` endpoint (`/api/v1/tls/ask`) returns 200 for verified domains and
  403 otherwise — prevents certificate-issuance abuse (verified pattern).
- Domain verification requires a DNS TXT record (`vsm-verify=<token>`); until
  verified, the domain is not served. Caddy admin API stays on localhost.

## BYOK (bring-your-own-key) envelope encryption

- Per-tenant Data Encryption Key (DEK, AES-256-GCM) generated at provisioning,
  wrapped by the platform master KEK (env) and stored wrapped in `tenant_keys`.
- `encryption_mode='byok'` tenants can supply their own KEK reference
  (KMS alias / key file); decryption only happens in process memory.
- Applied to high-risk secrets (integration/webhook secrets, documents), not to
  lookup columns (email/phone stay searchable; documented tradeoff).

## Throttling (noisy neighbor)

- Per-tenant Redis fixed windows, limits by plan (free 60/min, pro 300/min,
  enterprise 1200/min), `429` + `Retry-After`. Login: 10/min per IP.
- Redis outage → fail-open **with an ERROR log** (availability bias; documented).

## Compliance notes

- **EU Accessibility Act**: enforceable since 2025-06-28; standard EN 301 549 →
  **WCAG 2.2 AA**. Frontend uses semantic HTML, keyboard operability, visible
  focus, labeled controls, 4.5:1 contrast, reduced-motion support.
- GDPR posture: per-tenant data export/delete endpoints; region pinning via
  `tenants.region`; audit trail for personal-data access; minimize PII in logs
  (tenant/user IDs only, never emails or payloads).
- Audit log: append-only business events (`audit_logs`) — who/when/what/entity.

## Operational security checklist (production)

- [ ] `JWT_SECRET`, `MASTER_KEK_B64`, DB passwords: real random values, rotated.
- [ ] TLS everywhere (automatic via Caddy); HSTS on by default via Caddy headers? add if needed.
- [ ] Backups: `pg_dump` cron + tested restores (see RUNBOOK).
- [ ] `row_security = off` for backup/dump sessions to surface logic errors loudly.
- [ ] Monitor 429 rates per tenant (noisy neighbor), login failures, webhook signature errors.
