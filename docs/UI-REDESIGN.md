# UI Redesign Spec — Vehicle Service Manager

**Status:** verified spec, pre-implementation. 2026-10-18.
**Rule:** no UI file changes until the change is covered here (or this file is updated first).
Every rule below is backed by (a) research sessions S1–S10 (app dashboard patterns, 2026 palettes,
shadcn/Tailwind v4 tokens, pricing/landing, WCAG 2.2, academic dashboard literature, mobile PWA
patterns, data-dense typography, form UX — full notes in `/tmp/opencode/ui-research/notes.md`) and
(b) a live audit of this product (19 screenshots in `/home/md/src/.playwright-mcp/`,
`desktop-01..12`, `mobile-01..07`), run against the Docker stack at `http://localhost:8090`.

---

## 1. Audit findings (current state → target)

Runtime-verified facts (Playwright, 2026-10-18, tenant `demo` / Downtown Auto Care, pro plan):

| # | Finding | Evidence | Target (section) |
|---|---------|----------|------------------|
| A1 | Active nav item = full saturated teal fill; reads as a button, not a location | desktop-02, mobile-06 | §5.1: 8% brand tint + 3px accent bar |
| A2 | No dark mode at all (`color-scheme: light`, hex tokens only) | `globals.css:46` | §3: dark token set + Light/System/Dark setting |
| A3 | No `tabular-nums` anywhere; money/IDs flutter column width | desktop-03/04 | §4: numeric typography rules |
| A4 | KPI cards: no delta, no sparkline; "Revenue (30 days)" repeats "$508.78 this month" twice (redundant subtext) | desktop-02 | §7.4, §8: one number, one delta, one sparkline |
| A5 | "Orders by status" bars all the same teal — chart carries no meaning | desktop-02 | §8.3: fixed status hues + legend |
| A6 | Order detail: two solid teal primaries side-by-side ("Request parts" + "Mark completed"); "Cancel order" not destructive-styled | desktop-04 | §6.1: one primary per region; §7.6 |
| A7 | Truncated search placeholders ("Search number, vehicle, de…", "Search number or custome…") | desktop-03, desktop-07 | §6.6: short placeholders + min-width fixes |
| A8 | **Pricing drift: landing `$49` (`page.tsx:177`) + signup `"$49/mo"` (`signup/page.tsx:319`) vs backend catalog Pro `$29`, Enterprise `$99` (`alembic/versions/0001_initial.py:139-155`, served via `GET /settings/plans`)** | desktop-09/11, code | §7.1/§7.3: single source of truth = plans API (new public endpoint) |
| A9 | Landing: no product visual, no social proof, no FAQ; hero right column empty | desktop-11 | §7.1 |
| A10 | Full-page "Loading workspace…" on every hard navigation (auth re-check flash) | desktop-02 flow | §7.2: shell renders immediately, per-component skeletons |
| A11 | Mobile: no bottom tab bar (hamburger drawer only) | mobile-01..07 | §9.1: 4-tab bottom bar + More drawer |
| A12 | Mobile orders table overflows: Status/Priority/Total clipped off-screen | mobile-02 | §9.2: table→card list |
| A13 | Mobile order detail: horizontal page overflow (bottom scrollbar) + actions wrap to 2 rows | mobile-03 | §9.3: min-width:0 sweep + single action row logic |
| A14 | Mobile settings: 6 tabs wrap into a 2-row grid | mobile-04 | §9.4: scrollable underline tabs, 44px |
| A15 | Billing: Free card has no feature list (asymmetric vs Pro/Enterprise) | desktop-09 | §7.7 |
| A16 | Login heading is `h3` (should be page `h1`) | desktop-01, mobile-07 | §7.3 |
| A17 | Branding panel: "Save changes" always enabled (no dirty-state) | desktop-08 | §7.7 |
| A18 | Audit log + vehicles/customers/invoices pass structurally — keep, apply new tokens/table rules only | desktop-05/06/10 | §5.4 |

---

## 2. Principles (decision rules for the whole pass)

1. **Color = meaning. Nothing else.** Brand color identifies "this is actionable/location"; it never
   encodes status. Status hues are fixed across tenants (§3.4).  (S2, S5)
2. **Weight and space carry hierarchy, not color and size inflation.** 12px is the practical floor;
   only the hero metric qualifies as WCAG "large text" (≥24px). (S9)
3. **Three states for every data surface:** loading (shaped skeleton), empty (sentence + one CTA),
   error (component banner + retry). Never a bare spinner for a region. (S1, S4)
4. **Glanceable first:** one number, one delta, one sparkline per KPI; tables for reference data,
   cards for browsing, on mobile cards *become* the table. (S2, S5, S8)
5. **Quiet chrome, loud data.** Sidebar/toolbars dimmer than content; borders ~10% contrast; no
   shadows on metric cards. (S4, S5)
6. **Every movement documented:** validate on blur, errors persistent + actionable, labels always
   visible, 44px targets on touch. (S10)
7. **Accessibility is a gate, not a polish:** 4.5:1 text / 3:1 non-text, keyboard to 3rd level,
   200% zoom + text-spacing override on the busiest screens. (S7, S9)

---

## 3. Design tokens

### 3.1 Architecture (S3, S4)
3 layers, all in OKLCH, consumed only via Tailwind v4 `@theme inline` (`--color-*`):
`brand layer` (runtime, tenant-controlled: `--brand-primary`, `--brand-primary-fg`,
`--brand-accent`) → `semantic layer` (theme-aware: background/surface/text/status/sidebar) →
`component layer` (component CSS uses semantic tokens only). **Rule:** no raw palette classes
(`bg-teal-600`) in components; no token without a `-foreground` twin where it can host text.

Branding is applied at runtime by `lib/branding.tsx` (`readableOn()` picks fg); the redesign adds
`--brand-primary-hover` (color-mix 12% darker) and `--brand-primary-soft`
(`color-mix(in oklab, var(--brand-primary) 8%, transparent)`) so the tenant brand participates in
hover/active states without component hacks.

### 3.2 Light theme (replaces `globals.css:4-23`)
```
--background: oklch(0.985 0.002 85);   /* Cloud Dancer–adjacent canvas (S2) */
--foreground: oklch(0.21 0.02 265);
--card: oklch(1 0 0);
--muted: oklch(0.96 0.005 260);
--muted-foreground: oklch(0.45 0.03 260);   /* ≥4.5:1 on bg/muted/card — verify at impl */
--border: oklch(0.92 0.008 260);
--input: oklch(0.86 0.01 260);
--ring: var(--brand-primary);
--destructive: oklch(0.51 0.19 27);
--success: oklch(0.53 0.14 150);
--warning: oklch(0.56 0.13 63);
--info: oklch(0.51 0.21 262);
--sidebar: oklch(0.975 0.004 260);
--sidebar-foreground: var(--foreground);
--sidebar-hover: oklch(0.945 0.006 260);
--sidebar-active-bg: var(--brand-primary-soft);
--sidebar-accent: var(--brand-primary);
```

### 3.3 Dark theme (new; `.dark` class on `<html>`)
```
--background: oklch(0.155 0.01 260);   /* deep near-black neutral (S2 2026 direction) */
--foreground: oklch(0.97 0.003 260);
--card: oklch(0.21 0.012 260);         /* card LIFTS above background (S3) */
--muted: oklch(0.245 0.012 260);
--muted-foreground: oklch(0.73 0.02 260);
--border: oklch(1 0 0 / 10%);          /* white-alpha border (S3) */
--input: oklch(1 0 0 / 16%);
--destructive: oklch(0.70 0.17 22);
--success: oklch(0.77 0.16 152);
--warning: oklch(0.80 0.13 78);
--info: oklch(0.72 0.14 255);
--sidebar: oklch(0.185 0.011 260);
```
Mechanism (S3): blocking inline script in `<head>` (before paint) reads `localStorage('vsms.theme')`
with try/catch, applies `.dark`; `<html suppressHydrationWarning>`; `color-scheme: light dark`
instead of hard `light`. Setting lives in Settings → Appearance and the avatar menu:
**Light / System / Dark**, System = `matchMedia('(prefers-color-scheme: dark)')` live listener.
Charts render with `currentColor`-derived text so they inherit theme.

### 3.4 Status hues (fixed, both themes; NOT tenant-branded) (S2, S5)
```
--status-scheduled: oklch(0.58 0.15 255);   /* info blue */
--status-in-progress: oklch(0.72 0.15 75);  /* amber */
--status-awaiting-parts: oklch(0.60 0.17 300); /* violet — external dependency */
--status-completed: oklch(0.62 0.15 152);   /* green */
--status-invoiced: oklch(0.62 0.11 210);    /* cyan */
--status-cancelled: oklch(0.55 0.02 260);   /* neutral gray */
```
`Badge`/`StatusBadge` use these as *soft* fills (`color-mix 12% with card`) + 4.5:1 text variant of
the same hue; always dot/icon + text, never color alone (WCAG 1.4.1). Same ordering in the dashboard
chart legend and stacked bars.

### 3.5 Radii, spacing, motion
Radius: `--radius-card: 12px`, `--radius-control: 8px` (S4). Authed-app density is "comfortable":
table rows 48px, controls 36px desktop / 44px coarse-pointer. Motion: keep the existing 150–180ms
Radix animations + reduce-motion block (`globals.css:112-121`); sidebar width transition 200ms.

---

## 4. Typography (data-dense scale, S9)

### 4.1 Scale (replaces ad-hoc `text-sm/xs` in tables and cards)
| Token | Spec | Use |
|---|---|---|
| caption | 11px / 1.35 / 400 | timestamps, helper text under data |
| label | 12px / 1.35 / 500 | field labels, table headers (uppercase optional), badges |
| value | 14px / 1.45 / 400 | default UI text, table cells |
| value-emph | 16px / 1.4 / 600 | row titles, totals, counts |
| section | 18px / 1.35 / 600 | card headings |
| hero | 24px / 1.2 / 700 | page titles, KPI numbers |
Page `h1` = 20px/600 on mobile→hero on desktop stays 24/700; **only hero qualifies as WCAG large
text** (3:1); everything else needs 4.5:1 — this is why 18/600 headings must pass 4.5:1.

### 4.2 Numbers
- `font-variant-numeric: tabular-nums` on **all** numeric table columns, money, counts, dates,
  KPI numbers, and ID-ish columns (`SO-00014`, `BC-2468`, invoice numbers) — add
  `slashed-zero` to ID columns only; verify the resolved font ships `zero` (system stacks often
  don't → degrade gracefully, no layout dependency).
- Numeric columns: right-aligned, fixed `ch` width, `overflow: hidden; min-width: 0` on the cell.
- **Truncate labels, never numbers**; ellipsis requires `overflow:hidden` + `min-width:0` on the
  grid/flex ancestor (root cause of A7/A12).
- Formatting goes through the existing `lib/format.ts` only (one `Intl.NumberFormat` per kind):
  money 2dp; **deltas** `signDisplay:'exceptZero'`, `maximumFractionDigits:1` with ▲/▼ glyph
  (arrow = direction, color = good/bad — two separate facts, S5).

---

## 5. Layout & density

### 5.1 App shell (replaces `components/page.tsx` nav)
- Sidebar 256px, **collapsible to 64px rail** (icon-only, tooltips, persisted in localStorage);
  dimmer surface (`--sidebar`) than content.
- Nav item: 36px (44px coarse), radius 8, icon 18px + label 14/400; **active = 8% brand tint +
  3px left accent bar + 500 weight** (fix A1); hover = `--sidebar-hover`; focus ring on brand.
- Mobile (<880px): sidebar hidden; **bottom tab bar** (§9.1) + existing drawer for secondary nav.
- Header: 56px, sticky, backdrop blur, border-bottom; page title lives in content, not header.
- Content: `max-w-[1400px]`, 24px gutters, 12-col grid for dashboards, cards `minmax(200px,auto)`.

### 5.2 Loading behavior (fix A10)
Shell (sidebar/header) renders instantly after first auth check; route changes render the shell +
that page's own skeleton/`TableSkeleton`. Full-page "Loading workspace…" only on true cold start
(no token cached). No `loading.tsx` that blanks the shell.

### 5.3 Cards
Flat: 1px border, radius 12, padding 16 (20 for KPI), **no shadow**; hover only on interactive
cards (border darkens, cursor pointer). Section header pattern: 18/600 title + optional caption.

### 5.4 Tables (applies to orders, vehicles, customers, invoices, audit)
Sticky header (solid `--card` bg, z-10); row height 48px (min-height — WCAG 1.4.12, text-spacing
safe); zebra none — rely on row borders `--border`; row hover `--muted` 40%; sort indicators on
sortable columns; header cells 12/500 `--muted-foreground` (contrast-checked on the sticky bg, not
on white — trap #6b7280-on-#f4f4f5 = 4.40 fails, S9); pagination footer "Showing 1–20 of 214" +
Prev/Next, right aligned; keep required `caption` (sr-only variants allowed).

---

## 6. Components

### 6.1 Button hierarchy (fix A6)
- **One solid primary per view/region.** Order detail: the *next workflow action* is primary
  (scheduled→"Start work", in_progress→"Mark completed", awaiting_parts→"Resume work"), everything
  else outline/ghost.
- Duty map: primary = commit; outline = alternate; ghost = tertiary/in-row; **danger**
  (`--destructive`) solid reserved for confirm dialogs; in-page destructive = ghost-danger with
  icon ("Cancel order" → ghost-red + ConfirmDialog explaining consequences).
- Sizes: sm 32 / md 36; coarse-pointer min-height 44; icon-only buttons always `aria-label` +
  tooltip. Pressed/selected uses `aria-pressed`/`aria-selected` (exists already — keep).

### 6.2 Fields (S10 — form UX rules)
- Label always visible above control (12/500); placeholder only as format example; hint *before*
  typing; error on **blur**, below the field, plain-language fix, persistent until corrected,
  icon + text (never color alone), `aria-invalid` + `aria-describedby`, `role="alert"` on the
  change; success checkmarks on blur where useful.
- Single column; controls full-width on mobile; 16px min input font on mobile (no iOS zoom);
  8px min gap between adjacent targets; group with `fieldset`/`legend` when related.
- Correct `autocomplete` + `inputmode` on email/tel/search/code fields.
- Selects: 2–5 options → segmented/chips; 5–10 → select; 10+ → searchable combobox.
- Dialogs are focus-trapped, Esc closes, first field auto-focus; mobile → bottom sheet variant
  (drag handle, swipe dismiss). Sticky submit inside long/mobile forms.
- Multi-step (signup): step counter + progress + per-step validation; preserve entered data on
  back (already local-state — keep, add draft autosave to sessionStorage).

### 6.3 States (already exist — upgrade visuals)
`Skeleton` shaped to final layout (3 rows for tables, card outlines for KPI); `EmptyState` = icon +
one sentence + single primary CTA; `ErrorState` = inline banner with retry at component level;
`UpgradeNotice` keeps feature-gate role. All states must render inside the shell, not instead of it.

### 6.4 Badge / StatusBadge
Soft fill + dot + text (§3.4); `Badge` neutral tones stay for non-status metadata. Priority shown
as text (`titleCase`) + subtle weight only — not a second color scale competing with status (it is
already text-only; keep, ensure tabular alignment in tables).

### 6.5 Tabs (settings)
Desktop: underline tabs, 36px. Mobile: horizontal scroll (overflow-x, edge fade, 44px targets) —
**never wrap** (fix A14).

### 6.6 Search, filters, pagination
Short placeholders that fit: "Search orders", "Search invoices", "Search vehicles", "Search
customers" (full scope moves to the field's hint/aria-description; fixes A7); debounce 300ms
(existing `useDebounced`); filter chips: 32px desktop / 44px mobile, horizontal scroll on mobile
with edge fade, `aria-pressed`, result count line "14 orders" under the toolbar.

---

## 7. Page-by-page plan

### 7.1 Landing (`app/page.tsx`) — fix A8, A9
- **Pricing: single source of truth.** Add public read-only endpoint `GET /api/v1/public/plans`
  (catalog only: id, name, price, features, limits — no auth, no tenant data) and render pricing
  from it; correct values Free $0 / **Pro $29** / Enterprise $99, feature bullets derived from the
  same feature/limits JSON the app uses (kills the $49 drift everywhere). Signup step 1 consumes
  the same fetch; hardcode nothing.
- Hero: left copy + CTA ("Start free", verb-first); right = **real product screenshot** (capture
  the redesigned dashboard at 1440×900 during P6 and commit as `public/product/dashboard.png`;
  browser-frame styling, no fake UI).
- Sections: how-it-works (3 steps), feature grid grounded in actual capabilities (orders flow,
  invoices, audit log, white-label, API), pricing, FAQ (billing, free plan, data export, cancel
  anytime, who owns data), footer (product/legal/contact columns).
- Honesty constraint: no fabricated logos/testimonials; use "Built for independent workshops"
  positioning + "no card required" risk reversal near CTAs (S6).

### 7.2 App shell
Per §5.1/§5.2. Header keeps: hamburger (mobile), workspace switcher/name, user menu (+ theme
submenu, sign out). Drawer gains the theme toggle link and Settings.

### 7.3 Auth pages
- Login (`login/page.tsx`): heading becomes page `h1` (currently h3, fix A16); demo hint chip
  ("Demo workspace: demo / owner@demo.example / demo-password-123") shown only on `?demo=1` or
  when hostname is localhost; keep workspace prefill.
- Signup: keep 3-step wizard; add sessionStorage draft autosave; price strings from plans fetch;
  step indicator unchanged (em-dash for future steps is correct).

### 7.4 Dashboard (`app/app/page.tsx`)
- 4 KPI cards (responsive clamp 1/2/4): hero 24/700 number tabular; **one delta** ("▲ 12.4% vs
  prev 30 days") color = good/bad; **one sparkline** 1.5px stroke, no axis, brand-tint or
  neutral; container-query reflow at 300px.
- "Revenue (30 days)" duplicate subtext → replace with previous-period delta (fix A4).
- "Orders by status": bars stacked or grouped with fixed status hues (§3.4) + legend with counts;
  click-through to `/app/orders?status=x` (filter chips already model this).
- Every chart gets a text/table equivalent (title + summary line) for a11y.

### 7.5 Orders list (`app/app/orders/page.tsx`)
Desktop: keep table, apply §5.4 + tabular discipline (A3) + short placeholder (A7). Result count.
Mobile: card list (§9.2). "New order" stays the single primary.

### 7.6 Order detail (`app/app/orders/[id]/page.tsx`) — fix A6, A13
- Action logic per §6.1 (next-transition primary; "Request parts" outline; "Cancel order"
  ghost-danger + confirm).
- Totals block: right-aligned, tabular, subtotal/labor/parts/total hierarchy (total = 16/600).
- Items table → on mobile stacked definition rows (kind badge, description, qty×unit, line total
  right).
- Sweep for `min-width:0` / `overflow-x` sources so the page never scrolls horizontally at 390px.

### 7.7 Settings (`app/app/settings/page.tsx` + `components/settings/panels.tsx`) — fix A15, A17
- Tabs per §6.5. Panels reuse §5.3/§5.4.
- Billing: all plan cards render the same structure (price, feature bullets from
  `FEATURE_LABELS`, limits) → Free stops looking broken; current plan = badge + "Current" button
  state (not just disabled-looking).
- Branding: dirty-tracking — Save disabled until change, then confirm toast + live preview of
  tokens; color inputs show computed contrast warnings if a tenant picks a failing brand pair.
- Add Appearance section (Light/System/Dark) shipped in §3.3.

### 7.8 Audit, vehicles, customers, invoices
No structural changes (they pass): apply tokens, §4 numerics, §5.4 tables, §6.6 search. Invoices
placeholder shortened; audit timestamps tabular. Vehicle/customer rows stay non-clickable (no
detail routes exist — do not fake affordances).

### 7.9 Offline page
Align tokens/typography; keep minimal.

---

## 8. Dashboard data-viz rules (S5, Bach et al. 2022)
Parallel + hierarchical structure; KPI row (parallel) over detail charts; shared semantic color
(status hues); labels first, color second; max ~6 categories per chart; no 3D/pie beyond 5 slices;
grids `--border` 1px; chart text `--muted-foreground` (4.5:1 verified); numbers in charts tabular;
tooltips: label + value + period.

---

## 9. Mobile (≤880px, S8/S9)

### 9.1 Bottom tab bar (fix A11)
Fixed, 56px + `env(safe-area-inset-bottom)`, 4 items: **Dashboard, Orders, Vehicles, More**
(Icons 24px + 10px labels; active = brand color + tint pill; 44px+ hit areas; `aria-current`).
"More" opens the existing drawer (Customers, Invoices, Audit, Settings, theme, sign out).
Content gets `padding-bottom: 72px`. Tap active tab = scroll to top. Hamburger in header kept only
as secondary affordance.

### 9.2 Tables → cards (fix A12)
Orders/vehicles/customers/invoices render as stacked cards on mobile: line 1 = ID (tabular,
slashed-zero) + status badge; line 2 = title/service; line 3 = vehicle + customer; right column =
total (tabular). Whole card tap → detail; row actions via sheet. No horizontal scroll anywhere —
this is a 390px gate item.

### 9.3 Order detail mobile (fix A13)
Primary action full-width sticky above the tab bar; secondary actions collapse into a "More
actions" sheet; totals above the fold end; `min-width:0` sweep per §4.2.

### 9.4 Misc
Settings tabs scroll (§6.5); filter chips scroll; dashboards stack cards (delta+sparkline keep
KPI cards glanceable, no long empty scroll); pull-to-refresh deferred (PWA refresh button
suffices); destructive actions in sheets require confirm + undo toast where reversible.

---

## 10. Implementation plan (order matters)

| Phase | Scope | Files |
|---|---|---|
| P1 | Tokens, dark mode, typography utilities, theme script + setting | `app/globals.css`, `app/layout.tsx`, `lib/theme.tsx` (new), settings Appearance |
| P2 | UI kit: Button duties, Field (blur validate API), Badge/StatusBadge, Table numerics, states, Dialog/sheet, Tabs scroll | `components/ui/*` |
| P3 | Shell: sidebar collapse + active state, mobile bottom nav, loading behavior | `components/page.tsx`, `components/app-shell.tsx` |
| P4 | Dashboard KPI cards + status chart + formatter deltas | `app/app/page.tsx`, `lib/format.ts` |
| P5 | Pages: orders list/detail, invoices, vehicles, customers | per §7.5/7.6/7.8 |
| P6 | Landing/login/signup + `GET /public/plans` + hero screenshot capture | `app/page.tsx`, `app/signup/page.tsx`, `app/login/page.tsx`, `backend/app/api/routers/public.py`, `backend/app/schemas/billing.py` reuse |
| P7 | Verification sweep (§11) + fixes | all |

Backend touch is limited to the public plans endpoint (P6) + one test.

---

## 11. Verification protocol
1. **Build gates:** `npx tsc --noEmit`, `npm run build`, backend `pytest -q` (new endpoint test).
2. **Visual regression:** re-run the Playwright audit at desktop 1440×900 + mobile 390×844 on
   `:8090` after `docker compose build && up -d`; compare against `/home/md/src/.playwright-mcp`
   baseline; all A1–A18 closed or explicitly deferred here.
3. **Contrast:** compute all token text pairs (muted-fg on bg/muted/card/sidebar; status text on
   soft fills; brand-fg on brand) at both themes — 4.5:1 text, 3:1 non-text; only hero 24/700 may
   use 3:1.
4. **Zoom/text-spacing:** 200% zoom + text-spacing override (letter 0.12em, word 0.16em, line
   1.5, paragraph 2em) on dashboard + orders list + order detail: no clipping/loss.
5. **Keyboard:** tab through shell → nav → table → dialog (incl. focus trap, Esc) to 3rd level;
   visible focus everywhere.
6. **CWV budget (S7):** LCP ≤2.5s, INP ≤200ms, CLS ≤0.1 on dashboard (mobile emulation).
7. **Touch audit:** 390px pass — no horizontal scroll on any route; all targets ≥44px with ≥8px
   spacing; bottom bar doesn't overlap content.

## 12. Acceptance criteria
- All audit findings A1–A18 closed (A18 = tokens applied, structure kept).
- One visual language: OKLCH token system, both themes, brand runtime-compatible (test a second
  tenant brand color, e.g. deep blue, without editing components).
- Pricing identical everywhere (plans API), verified in browser at `/`, `/signup`, settings.
- Dashboard answers "how are we doing" in <5s: 4 KPIs with deltas + status chart with legend.
- Orders flow fully usable on a 390px phone without horizontal scrolling, primary action always
  visible, destructive guarded.
- Every component shows loading/empty/error states; no full-page spinner on navigation.

---

## 13. Verification log — zero-to-hero pass (2026-10-18)

Environment: dev `:3100`, production build `:3101`, backend via Docker `:8090`, Playwright 1440×900.

### 13.1 Contrast audit & token fixes (WCAG 1.4.3 / 1.4.11 / 2.4.13)

Computed-style audit (canvas-parsed colors, alpha composited, both themes) found four failures; all fixed and re-verified:

| Fix | Before | After |
|---|---|---|
| `--input`: light `oklch(0.86 0.01 260)` → `oklch(0.63 0.02 260)`; dark `white/16%` → `white/34%` | 1.64:1 (card, dark) | 3.14:1 ✓ (non-text ≥3:1) |
| New `--brand-text`: light = `--brand-primary`; dark = `color-mix(in oklab, var(--brand-primary) 55%, white)` | 3.57:1 (dark, on bg) | 8.38:1 ✓ |
| New `--success-foreground` | white on success chip 1.81:1 (signup) | 10.01:1 dark / 4.97:1 light ✓ |
| Placeholder mix 70% → 85% (`ui/fields.tsx`) | 4.28:1 (dark) | 5.67:1 ✓ |

Usage rule: `--brand-text` for brand-colored **text** (button `link` variant, auth links, landing icon link); `--brand-primary` stays for fills/rings (white on brand = 5.47:1 ✓). Ring ≥3:1 focus indicator holds (3.57 dark / 5.25 light on bg).
Files: `app/globals.css`, `components/ui/{fields,button}.tsx`, `app/login/page.tsx`, `app/signup/page.tsx`, `app/app/page.tsx`, `app/page.tsx`.

Post-fix pairs (dark / light): brand-text 8.38/5.25 on bg, 7.62/5.47 on card, 6.94/4.88 on muted; input 3.14/3.49 on card, 3.06/3.34 on bg; placeholder 5.67/5.06 on card, 6.16/4.88 on bg; success-fg 10.01/4.97 — all pass.

### 13.2 Console sweep

Routes: `/`, `/login`, `/signup`, `/app`, `/app/settings`, `/app/orders`, `/app/orders/[id]`, `/app/invoices`. No errors (dev: HMR/DevTools info only); production console: zero messages.

### 13.3 Auth bootstrap (by design, hardening noted)

Reloading an app route does `GET /auth/me` → 401 → `POST /auth/refresh` → retry (200): the intended transparent-refresh flow; React StrictMode doubles it in dev only. Bootstrap currently requires the localStorage access token (`lib/auth.tsx:49`) — an HttpOnly refresh cookie alone does not restore a session on a fresh origin. Deferred hardening (memory-only access token + boot refresh + cross-tab coordination) is tracked in `docs/FEATURE-ROADMAP.md` §4; refresh-token rotation makes concurrent boot refresh racy without a BroadcastChannel.

### 13.4 Keyboard

First Tab lands on "Skip to content"; Enter moves focus to `#main` (URL `#main`) — WCAG 2.4.1 bypass blocks pass at shell level.

### 13.5 Production build & smoke

`npm run build` passes (14 routes, in-build TS clean). Prod smoke `:3101`: `/`, `/login`, `/signup`, `/app` → 200; login E2E through the prod proxy → dashboard loads; console clean.
Note: `BACKEND_INTERNAL_URL` is baked at build time (`frontend/next.config.ts:5`). Local prod runs must pass it to `npm run build` (e.g. `BACKEND_INTERNAL_URL=http://localhost:8090 npm run build`); the Docker image already passes it as a build arg.

### 13.6 Fixes from this pass

- `app/login/page.tsx:45` — removed the unconditional `demo` workspace fallback (it rendered in the Workspace field for every visitor). Now `workspaceSlug() ?? (demo ? "demo" : "")`; `?demo=1` still pre-fills slug + credentials, matching README:41.

### 13.7 Still open (plan unchanged)

P3 mobile shell, P4 dashboard chart/KPI deltas, P5 tables→cards, P6 landing/pricing/plans API/print styles; the full §11 protocol (390px touch pass, 200% zoom, CWV budget, dialog focus trap) runs at P7.

## 14. Tier A feature pass (2026-10-19)

Scope: roadmap Tier A — plans API/pricing consistency, estimates with online approval, VIN decode,
customer status link, print. Backend tests: `backend/tests/test_features.py` (5 tests, suite 20 passed).

### 14.1 Public surfaces

- `/status/[token]` and `/estimate/[token]` are client components wrapped in thin server pages;
  both read the token from `useParams()` and share `PublicShell` (workspace logo, name and brand
  colours applied with `readableOn` for contrast).
- Status page shows the five-step timeline, vehicle, schedule and line items as kind + description
  only — no prices. Estimate page shows prices, totals and approve/decline; unknown or revoked
  tokens render "This link is invalid or has expired" with a retry action.
- Both pages carry `metadata.title` so shared links have a readable tab/OG title.

### 14.2 Staff surfaces

- Estimates list/detail added to the sidebar between Service orders and Invoices; detail supports
  line-item add/remove, send/reissue, copy/revoke, edit, delete draft, print and a converted-order
  link.
- Order detail gained "Share status link" (creates, copies, shows Copy/Revoke) and Print; both are
  `print:hidden` alongside the breadcrumb so paper output contains only the job sheet.
- Invoice preview dialog prints via the same stylesheet: overlay hidden, panel flattened, close
  button suppressed.
- Vehicles add-dialog decodes VIN on demand and autofills make/model/year/fuel; the button is
  disabled until 17 characters are present.

### 14.3 Verification

- `npm run typecheck` and `npm run build` clean; routes include `/app/estimates/[id]`,
  `/status/[token]`, `/estimate/[token]`.
- Browser E2E (1440×900, demo tenant): pricing shows $0/$29/$99 from the API; estimate ES-00001
  created → line item → sent → approved publicly → order SO-00015 with copied items; status link
  renders without prices and 404s after revoke/invalid token; VIN `1HGCM82633A004352` decoded to
  HONDA Accord 2003.
- Backend image rebuilt; `alembic current` = `0002 (head)`; short VIN returns 422 with the friendly
  message.

### 14.4 Remaining after Tier A

P3 mobile shell, P4 dashboard chart/KPI deltas, P5 tables→cards, P7 full protocol (390px touch,
200% zoom, CWV budget, dialog focus trap) remain open. Tier B (Stripe, SMS, DVI, booking, review
requests) is next per `docs/FEATURE-ROADMAP.md`.

## 15. Tier B feature pass (2026-10-19)

Scope: roadmap Tier B — Stripe invoice payments, SMS notifications, DVI with photos, online booking,
review requests. Backend tests: `backend/tests/test_tier_b.py` (7 tests, suite 27 passed).

### 15.1 Public surfaces

- `/book/[slug]` (`booking-view.tsx`): day-grouped slot picker (`Mon 19 Oct` + `9:00 AM` labels in
  the workshop timezone), customer/vehicle form, honeypot field hidden from view and a11y tree, and
  a booking confirmation with the order number.
- `/status/[token]` gained an inspection summary (items, condition chips, note, photos served
  through the token-scoped proxy).
- `/review/[token]` (`public-views.tsx`): star rating widget, optional comment, thank-you state
  linking to the workspace's public review URL. Double submission returns 409.

### 15.2 Staff surfaces

- Order detail: "Start inspection" opens `inspection-panel.tsx` — item rows (description,
  condition, note), photo upload with thumbnails, complete/locks the inspection; completed date uses
  `formatDate` for consistency. "Request review" sends the tokenized link (re-request rotates the
  token and re-sends the SMS).
- Invoices list: "Payment link" mints a Stripe Checkout URL; without a configured provider the 409
  guidance renders inline.
- Settings → Operations (booking on/off, business hours editor, review URL) and Settings →
  Notifications (test SMS form, outbox table with skipped/failed states).

### 15.3 Verification

- `npm run typecheck`/`npm run build` clean; suite 27 passed; `alembic current` = `0003 (head)`.
- Browser E2E (1440×900, demo tenant): booking `SO-00016`/`SO-00017` with `Mon 19 Oct, 4:00 PM`
  confirmation and outbox SMS; review request on `SO-00010` → 5-star submission → Google link;
  DVI on `SO-00010` (item + photo + locked); share link renders the inspection publicly; payment
  link on `INV-00002` surfaces the 409 guidance.
- Fixes found by the pass: slot labels 12-hour (`slot_label` shared by the slots feed, the booking
  confirmation and the SMS), re-requests re-send the SMS, review SMS links are absolute via
  `PUBLIC_APP_URL`, inspection form places the note before "Add".

### 15.4 Remaining after Tier B

P3–P7 from §11/§13.7 remain open. Tier C (inventory/parts, accounting sync, marketing/CRM,
multi-location, PWA) is next per `docs/FEATURE-ROADMAP.md`.

## 16. Tier C inventory pass (2026-10-19)

Scope: first Tier C item — parts catalog with stock levels, reorder alerts, cost/price and an
append-only stock ledger wired into order line items. Backend tests: `backend/tests/test_inventory.py`
(4 tests, suite 31 passed).

### 16.1 Staff surfaces

- `/app/inventory`: stat cards (active parts, low stock, stock value at cost), search by name/SKU,
  "Low stock only" filter, and a table with stock/reorder/cost/price plus row actions (adjust, edit,
  archive). Add/edit dialogs keep opening stock on create only; archiving is a soft deactivate.
- Adjust dialog records a signed ledger entry: "Receive stock" (`received`) or "Adjust out"
  (`adjustment`), with an optional note ("Delivery, count correction…").
- Order detail add-item form: choosing Kind = Part reveals "From stock"; selecting a part autofills
  description and unit price and shows the live stock hint. Removing a line or cancelling the order
  returns the linked quantities to stock.
- Sidebar: Inventory entry is gated by the `inventory` entitlement (pro/enterprise; free sees an
  upgrade card on the page and no nav item).

### 16.2 API and data

- `/api/v1/inventory`: parts list (search/category/low_stock/pagination), categories, create,
  update, archive, stock adjust, movements, summary.
- `parts` + `stock_movements` are tenant-scoped with FORCE RLS; `service_items.part_id` is an
  optional FK (`ON DELETE SET NULL`). Stock changes only flow through the ledger service, which
  rejects negative stock with 409 and quantizes to 2 decimals.
- Entitlement `inventory` added by migration `0004` (pro/enterprise true, free false). SKUs are
  auto-generated (`P-0001…`) when omitted; writes require owner/admin/manager and audit as
  `inventory.part_created|part_updated|part_deactivated|stock_adjusted`.

### 16.3 Verification

- `npm run typecheck`/`npm run build` clean; suite 31 passed; `alembic current` = `0004 (head)`;
  `/api/v1/livez` healthy through Caddy.
- Browser E2E (1440×900, demo tenant, `SO-00018`): created `LIVE-BP-1` (stock 6), added 2 via API
  and 1 via the picker (stock 4 → 3, autofilled "Front brake pad set" / $79.00), received 1 via the
  adjust dialog (stock 4, toast "Stock received"), cancelled the order (stock 7, two `returned`
  movements). A 6-unit `adjustment` dropped stock to 1, showing the Low badge, `Low stock 1` and the
  filtered empty/non-empty states; a 5-unit receive restored stock to 6.
- Fixes found by the pass: the add-item request dropped `part_id` (line saved unlinked), picker
  stock hints needed `Number(...).toLocaleString()`, and inventory SWR had to revalidate after
  adding/removing items or cancelling an order.

### 16.4 Remaining in Tier C

Accounting sync (§17), marketing/CRM automation (§18) and multi-location (§19) followed and are
shipped; PWA installability/push and supplier integrations remain per `docs/FEATURE-ROADMAP.md`.
P3–P7 from §11/§13.7 also remain open.

## 17. Tier C accounting sync (2026-10-19)

Scope: second Tier C item — post paid invoices to QuickBooks Online or Xero, and keep a mapped
journal CSV as the keyless fallback. One accounting connection per tenant; the provider is fixed
per deployment (`ACCOUNTING_PROVIDER=stub|quickbooks|xero`, default `stub`).

### 17.1 Staff surfaces

- Settings → Accounting (visible with `accounting_sync`, pro/enterprise): provider card with
  connection status, external company id, last sync time, and connect/disconnect.
- Connecting a real provider redirects to the provider's OAuth screen; the callback lands back on
  `/app/settings?tab=accounting`, exchanges the code server-side, and stores encrypted tokens.
- Account mapping fields: payment/undeposited-funds, income, and tax account codes. Defaults
  `1000` / `4000` / `2200`; editable before or after connecting.
- "Sync now" takes a paid-date range (defaults to month-to-date), posts one journal per paid
  invoice, and lists sync runs with status, invoice count, total and failure detail.
- "Download journal CSV" exports the same debit/credit lines for the chosen range without OAuth.
- Free plan sees the upgrade card in place of the panel; settings tab is hidden by entitlement.

### 17.2 API and data

- `/api/v1/accounting`: `GET /` (provider, configured, connection, pending invoices, last run),
  `POST /connect`, `POST /callback`, `PATCH /connection` (account mapping), `DELETE /connection`,
  `POST /sync`, `GET /runs`, `GET /export`.
- `accounting_connections` (one per tenant, FORCE RLS): provider, status, external company id,
  AES-GCM-encrypted access/refresh tokens, expiry, mapping JSONB, `last_synced_at`.
- `accounting_sync_runs` + `accounting_sync_items` (FORCE RLS): period, status, counts, total,
  detail; items map each invoice to its external journal id. Successful items make re-syncs
  idempotent; the connection row is locked during a run so two syncs cannot post duplicates.
- Journals: debit payment account for the invoice total, credit income for subtotal and tax for
  `tax_amount` (two lines when tax is zero). QBO `JournalEntry`, Xero `ManualJournal`, stub returns
  a synthetic id. OAuth state is a short-lived signed token bound to tenant + provider.
- `accounting_sync` entitlement added by migration `0005` (pro/enterprise true, free false).
  Mutations require owner/admin and audit as `accounting.connected|disconnected|mapping_updated|
  synced|sync_failed`. Tokens are never serialized.
- Missing provider credentials return 409 guidance (same pattern as Stripe/online payments);
  `stub` is always configured so local dev and tests stay keyless.

### 17.3 Verification

- Backend: `tests/test_accounting.py` (4 tests, suite 35 passed) covers free-plan 402 then pro
  unlock, stub connect + mapping + paid-invoice sync (1 invoice, $100.00), idempotent re-sync (0
  invoices), journal CSV contents, disconnect, cross-tenant isolation, and the 409 guidance when a
  real provider has no credentials.
- Migration `0005` applied on the dev stack; `GET /api/v1/accounting` on the demo tenant returns
  `provider: stub, configured: true, connection: null, pending_invoices: 1` before connecting.
- Browser pass (demo tenant, 2026-10-19): connected the stub, saved mapping `1010/4010/2210`,
  synced INV-00001 ($508.78 = $470.00 income + $38.78 tax), re-synced with "Nothing new to sync",
  downloaded `accounting-journal-2026-10-01-2026-10-19.csv` with three balanced lines, then
  disconnected via the confirm dialog — history retained and the paid invoice returned to pending.
  Screenshot: `.playwright-mcp/accounting-sync.png`.

## 18. Tier C marketing / CRM campaigns (2026-10-19)

Scope: third Tier C item — turn existing customer and service history into targeted SMS/email
campaigns through the notification outbox. No new delivery provider: campaigns ride the same
config-gated channel as reminders, so unconfigured providers record `skipped` rows instead of
failing. Entitlement `marketing` (pro/enterprise), added by migration `0006`.

### 18.1 Staff surfaces

- Marketing (sidebar, visible with `marketing`): campaign list with status, channel, audience
  size, sent/skipped/failed counts and created time.
- "New campaign" dialog: name, channel (SMS/email), segment (`all` customers, `inactive` — no
  order in N days, `due_service` — last completed service older than N days), lookback days,
  and message body with `{name}` / `{shop}` placeholders.
- Audience preview shows the reachable recipient count (customers with a phone for SMS or email
  for email) before sending; sending is one-shot from a draft and writes one outbox row per
  recipient.
- Campaign detail lists recipients with per-recipient status and provider error, linking back to
  the outbox semantics staff already see in Settings → Notifications.

### 18.2 API and data

- `/api/v1/campaigns`: `GET /` (paginated list), `POST /` (draft), `GET /{id}` (detail with
  recipients), `POST /preview` (reachable-audience count for a segment without saving),
  `POST /{id}/send`, `DELETE /{id}` (draft only).
- `campaigns` (FORCE RLS): name, channel, segment, lookback_days, body, status (`draft|sent`),
  counts, `sent_at`. `campaign_recipients` (FORCE RLS): customer, recipient address, status
  (`pending|sent|failed|skipped`), notification id, error.
- Segments are computed server-side from `customers` + `service_orders`; recipients are limited
  to customers reachable on the chosen channel, and a send is capped at 500 recipients (422 when
  the segment is wider, asking staff to narrow the lookback).
- Mutations require owner/admin and audit as `campaign.created|sent|deleted`.

### 18.3 Verification

Verified on 2026-10-19 against the dev stack and demo tenant.

- `backend/tests/test_campaigns.py`: entitlement 402 → pro upgrade → 200; segment math for
  `all`/`inactive`/`due_service` (a completed order is backdated 200 days with a direct admin
  connection so the windows are deterministic); preview counts split segment customers from
  channel-reachable recipients; send writes one `skipped` outbox row per recipient when no SMS
  provider is configured and records `sent_at`; re-send is 409; sent campaigns 409 on delete;
  draft delete is 204; empty audience is 422 with guidance; tenant B cannot list or read tenant
  A's campaign. Suite **40 passed**.
- Browser E2E (demo, Pro): Marketing appears in the sidebar; "New campaign" dialog auto-previews
  the audience (`Reaches 10 of 10 customers`); saving creates a Draft row; Send shows
  `This will reach 10 customers by SMS`, then the row flips to Sent with `0 sent · 10 skipped`
  and the toast explains no provider is configured; detail lists all 10 recipients as Skipped
  with `SMS provider is not configured`; switching the segment to Due for service reveals the
  180-day lookback field, shows the zero-audience message and disables Save. Screenshot:
  `.playwright-mcp/marketing-campaign.png`.
- Audit and outbox confirmed in Postgres: `campaign.created`/`campaign.sent` rows, and 10
  `notifications` rows with `template='campaign'`, `status='skipped'`.
- Frontend `npm run typecheck` and `npm run build` clean.

## 19. Tier C multi-location (2026-10-19)

Scope: a tenant can run more than one shop location. Tenant isolation is unchanged — RLS still
scopes every row by `tenant_id`; locations are an operational dimension so staff can assign and
filter service orders per site. Customers and vehicles stay shared across locations (a customer
may visit any branch), and inventory/staff scheduling remain tenant-wide in v1. Multi-location is
available on every plan; it is workflow depth rather than a plan gate.

### 19.1 Staff surfaces

- Settings → Locations (owner/admin; managers can view): list of locations with name, address,
  phone and a Default badge; create/edit dialog; "Make default" action; delete is refused while
  orders reference the location, when it is the last location, or when it is the default.
- Service orders: the create dialog gains a Location select (pre-filled with the default
  location), the list gains a Location column and a location filter next to the status chips.
  Orders created before a location existed, or after all locations are deleted, show "—".
- The default location is provisioned automatically ("Main location") for new tenants and
  backfilled for existing tenants by migration, so assignment is never required to create an
  order.

### 19.2 API and data

- `/api/v1/locations`: `GET /` (all staff roles, active first), `POST /` (owner/admin),
  `PATCH /{id}` (owner/admin), `DELETE /{id}` (owner/admin). Deleting a location referenced by
  orders returns 409 with guidance to keep it for history.
- `locations` (FORCE RLS): name (unique per tenant), address, phone, `is_default`, timestamps.
  Exactly one default per tenant is enforced by the service (setting a default clears the flag
  on siblings in the same transaction).
- `service_orders.location_id` (nullable, `ON DELETE SET NULL`, indexed with `tenant_id`) is
  assigned from the payload or the tenant default on create; `GET /service-orders` accepts
  `location_id` and list items include `location_name`.
- Migration `0007` creates the table + RLS + grants, seeds "Main location" for every existing
  tenant, and backfills every existing order to that location. Provisioning creates the default
  location for new tenants.
- Mutations audit as `location.created|updated|deleted|default_changed`; reads are open to all
  staff roles.

### 19.3 Verification (2026-10-19)

- Backend: `backend/tests/test_locations.py` (4 tests) covers the provisioning default, CRUD
  rules (duplicate name 409, unset default 422, delete last/default/referenced 409), manager
  write refusal (403), order create falling back to the default, list filtering, and
  cross-tenant isolation — suite **44 passed**. Migration applied to the dev stack
  (`alembic_version = 0007`): demo tenant seeded with "Main location" and all 18 existing
  orders backfilled.
- Browser E2E on the demo tenant (owner): Settings → Locations showed "Main location" with the
  Default badge; added "North Branch" (12 Cedar Ave, +1-555-0300) → "Location added"; "Make
  default" moved the badge → "North Branch is now the default location"; deleting Main location
  was refused with the 409 guidance ("This location has service orders; keep it for history")
  while the dialog stayed open; default was flipped back to Main location.
- Orders: the list gained the Location column and "Filter by location" select; a new order
  ("Locations E2E — wheel noise at North Branch") was created with the Location select
  pre-filled "North Branch (default)"; filtering by North Branch returned just that order; the
  detail edit dialog showed the current location and moving the order to Main location saved
  with "Order updated" (API re-check: `location_id` filter total 19, each item with
  `location_name`).
- Postgres audit confirms `location.created` ×1 and `location.default_changed` ×2 from the
  session. Frontend `typecheck` + `build` clean. Screenshots:
  `.playwright-mcp/locations-settings.png`, `.playwright-mcp/locations-orders-filter.png`.

## 20. Tier C PWA installability + staff push notifications (2026-10-19)

Scope: close roadmap row 14 — verify (and fill gaps in) installability, then add staff-facing
Web Push so people who install the app get pinged for events that need a human now. No new plan
gate: push rides the deployment's own VAPID keys, not a paid provider, so every plan gets it
(SMS and campaigns keep their entitlements).

### 20.1 Installability

Already present: `public/manifest.webmanifest`, `public/sw.js` (static-asset cache + offline
navigation fallback; API and cross-origin requests are never cached), 192/512/maskable icons,
`/offline` page, `SWRegister`, `appleWebApp` metadata. Gap-closing:

- Manifest gains `id: "/"`, `lang`, `dir`, `categories`, `prefer_related_applications: false`.
- `metadata.icons.apple` supplies the iOS home-screen icon.
- Verified in a real browser: manifest resolves with all fields, the service worker registers
  and controls after a reload, and an offline navigation renders the offline page. No PWA
  plugin: the hand-rolled worker stays because a generated one would add runtime caches this
  product deliberately does not want for tenant data.

### 20.2 Push (staff devices, v1)

- VAPID: `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` envs; when unset the backend
  generates a P-256 keypair once and persists it in registry table `push_config` (single row,
  private key encrypted with `MASTER_KEK` through `crypto.encrypt_secret`) so dev and keyless
  deployments work out of the box. Delivery uses `pywebpush`; if the package is absent,
  `GET /push/config` reports `enabled: false` and the UI hides the enable button.
- `push_subscriptions` (FORCE RLS, tenant-scoped): one row per browser — endpoint (unique per
  tenant), `p256dh`/`auth` keys, optional user agent, user FK cascade. Re-subscribing the same
  endpoint moves it to the current user (upsert on `(tenant_id, endpoint)`).
- API: `GET /push/config` (any signed-in staff), `GET /push/subscriptions` (own devices;
  owner/admin see the tenant's), `POST /push/subscriptions` (upsert), `DELETE
  /push/subscriptions/{id}` (own device, or owner/admin), `POST /push/test` (caller's own
  devices; returns `{sent, failed}` so a provider problem is visible instead of silent). No
  audit rows (personal device config, not a tenant data change) and no entitlement (see scope).
- Service `send_to_users` joins the users' subscriptions and posts the encrypted payload with
  `pywebpush.webpush` in a worker thread; `404/410` deletes the dead row (permission revoked),
  other failures are logged and counted — never raised, so a bounced push cannot fail a request.
  Triggers v1:
  - public booking request → owner/admin/manager, "New booking request"
  - order created or reassigned with a mechanic → that mechanic, "Service order assigned to you"
- Frontend: Settings → Notifications gains a "Push notifications on this device" card (states:
  unsupported / blocked by the browser / off / on, device list with remove, send test). The
  service worker adds `push` + `notificationclick` handlers; clicking a notification focuses an
  open tab or opens the order deep link.

### 20.3 Data & migration

`0008_push.py`: `push_config` (registry) + `push_subscriptions` (RLS policy + grants), downgrade
drops both. Provisioning is unchanged (keys are deployment-wide, subscriptions are per device).

### 20.4 Verification (2026-10-19)

- **Gates:** `backend/tests/test_push.py` + full suite **49 passed** (covers config generation,
  upsert-per-endpoint, ownership scoping for mechanic vs owner, test-send counts, 410 pruning and
  both triggers); `npm run typecheck` and `npm run build` clean.
- **Deployed stack:** migration `0008` applied; `GET /api/v1/push/config` returns
  `enabled: true` with the generated public key, no env keys present.
- **Browser (prod build, `next start`):** manifest fields resolve (`id`, `start_url`, `standalone`,
  192/512/maskable icons, `categories`, `prefer_related_applications: false`); the worker registers,
  activates and controls the page; `PushManager` is available. Stopping the web server and
  reloading renders the offline page (icon, message, Retry).
- **Push E2E:** a subscription created through the API with real P-256 keys received encrypted
  requests (`Content-Encoding: aes128gcm`, `Authorization: vapid …`) from three separate flows:
  Settings → Send test (toast “Test notification sent to 1 device”), a public booking request
  (`SO-00020`, staff alert) and reassigning that order to a mechanic (mechanic alert, separate
  device). Removing a device shows “Device removed” and drops the row; with notification
  permission denied the enable action explains that the browser is blocking notifications.
- **Implementation note:** `pywebpush` treats a string `vapid_private_key` as base64 DER, not PEM;
  the service builds `py_vapid.Vapid.from_pem(key.encode())` once per send. Keep that when touching
  `services/push.py`.

## 21. Tier C supplier catalog (2026-10-19)

Scope: close roadmap row 10 — parts supplier integration. The US market leaders (PartsTech,
NexPart, WHI) only expose partner APIs behind commercial onboarding, with no public contract to
implement safely. V1 therefore ships the integration seam plus two keyless providers that cover
real workflows today:

- `stub` — a small built-in distributor catalog for development, tests and demos.
- `csv` — the tenant uploads a distributor price list; search and import run against it. This is
  the region-neutral path (any supplier can export a CSV), and partner APIs can be added later as
  extra providers without schema changes.

Purchase-order transmission stays out of v1: each connection carries an optional portal URL and
the offer row links out to it, so the buyer orders at the supplier; receiving remains the inventory
"received" movement.

### 21.1 Data

- `supplier_connections` (FORCE RLS): name (unique per tenant), provider `stub|csv`, optional
  `portal_url`, timestamps.
- `supplier_catalog_items` (FORCE RLS): connection FK cascade, `sku`, brand, description, cost,
  price, stock_qty; unique `(connection_id, sku)`. Only the `csv` provider stores rows.
- Migration `0009`: both tables + policy + grants; `suppliers` feature added to pro/enterprise
  (false on free). Downgrade drops the feature key and both tables.

### 21.2 API (feature `suppliers`)

- `GET /suppliers` — connections with provider, catalog size, portal URL (any staff).
- `POST /suppliers` — create (owner/admin); provider validated.
- `DELETE /suppliers/{id}` — delete + cascade catalog (owner/admin).
- `POST /suppliers/{id}/catalog` — CSV upload for `csv` connections (owner/admin). Header
  `sku,description` required, optional `brand,cost,price,stock`; quoted fields supported; rows
  upserted on `(connection, sku)`; invalid rows skipped and counted; 2 MB / 5,000-row cap.
- `GET /suppliers/search?q=` — normalized offers across the tenant's connections
  (`connection_id`, `supplier`, `sku`, `brand`, `description`, `cost`, `price`, `stock_qty`,
  `portal_url`); max 50. `stub` serves its in-code catalog; `csv` does a case-insensitive match on
  SKU/description/brand.
- `POST /suppliers/import` — `{connection_id, sku}`: resolve the offer again and upsert the
  inventory part by SKU (create with stock 0, or update brand/supplier/cost/price); returns
  `{part_id, created}`. Audit `supplier.part_imported`.
- Audits: `supplier.created|deleted|catalog_imported|part_imported`.

### 21.3 UI

Sidebar gains **Suppliers** (visible only with the entitlement). `/app/suppliers`:

- "Supplier connections" card: provider badge, catalog size, portal link, delete; owner/admin see
  Add supplier and, for `csv`, Import CSV (file picker + result toast with imported/updated/
  skipped counts and the expected header).
- "Search supplier catalogs" card: debounced query (2+ chars), table with supplier, part, brand,
  cost, price, stock and an Import action; success toast distinguishes created vs updated;
  portal link per row when configured. Empty states explain how to add a connection.

### 21.4 Verification

- `backend/tests/test_suppliers.py` (4 tests): entitlement 402 on free; stub search + import
  creates then updates the part; CSV import counts, re-upload idempotence, header/stub/404/RBAC
  errors and audit entries; tenant isolation. Suite **53 passed**.
- Frontend `npm run typecheck` + `npm run build` clean (`/app/suppliers` static route).
- Migration `0009` applied on the dev stack (`0008 -> 0009` in the backend entrypoint log);
  `/api/v1/livez` 200.
- Prod-build E2E on the demo tenant (pro): nav entry, add CSV supplier with portal URL, upload
  3 valid + 2 invalid rows → toast "Catalog imported: 3 new, 0 updated, 2 skipped" and catalog
  size 3, search "oil" found `RPC-OIL-220` at cost $7.25 / price $14.50 / stock 32, Import → toast
  and an inventory part carrying supplier/brand/cost/price; deleting the connection cascades the
  catalog while keeping imported parts. The hidden file input is `aria-hidden` and not tabbable.

## 22. Email delivery channel (2026-10-19)

Scope: make the `email` notification channel real. Campaigns already accepted email recipients
but every row was recorded as skipped. Email now runs through deployment-level SMTP, mirroring
the SMS gate: with no credentials, business-event and campaign rows land as honest `skipped`
rows while the test probe returns 409 guidance — never a failed request. No per-tenant
mailboxes and no entitlement — the operator owns the relay.

### 22.1 Config

`SMTP_HOST` and `SMTP_FROM` enable the channel; `SMTP_PORT` (587),
`SMTP_USERNAME`/`SMTP_PASSWORD` (optional for trusted relays), `SMTP_SECURITY=starttls|ssl|none`
(default `starttls`, system trust store), `SMTP_TIMEOUT` (10s). `SMTP_FROM` may include a
display name (`Shop <no-reply@shop.example>`).

### 22.2 Behaviour

- `send_email` builds a plain-text `EmailMessage` (UTF-8, Date header) and runs `smtplib` in a
  worker thread; provider errors return `(failed, message)` truncated to 500 chars, like SMS.
- `queue_notification(channel="email")` sets provider `smtp` and status sent/failed/skipped, with
  `sent_at` on success; campaign delivery needs no change. Templates map to subjects (`test` →
  "Test message").
- `POST /notifications/test` takes `channel` (`sms` default) and a 254-char `to`; SMS keeps the
  `sms_notifications` entitlement, email is ungated, and the 409 names the missing envs.
- Settings → Notifications gains a Channel select (SMS/Email); the To field switches between
  tel/email and the outbox lists channel per row.

### 22.3 Verification

- `backend/tests/test_email.py` (5 tests): unconfigured email returns 409 with env guidance and
  does not persist a probe row; a monkeypatched transport asserts From/To/Subject/body and
  `smtp`/`sent`/`sent_at`; transport errors record `failed` with the error text; an unknown
  `SMTP_SECURITY` fails cleanly; a campaign email send flips recipients to `sent`. Suite
  **58 passed**.
- Frontend `typecheck` + build clean; Settings → Notifications channel select exercised in the
  prod build E2E (409 guidance without SMTP; sent path covered by the offline transport tests).
