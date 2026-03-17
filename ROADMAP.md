# Finance Hub v2 — Product Roadmap

*Consolidated March 17, 2026. Integrates original feature benchmark, ChatGPT product critique, and current build state.*

---

## Product Thesis

Finance Hub is an import-first, self-hosted finance app designed for high-trust transaction review, strong normalization and rules, reliable balance tracking, and optional AI assistance that improves workflow without becoming a hidden source of truth.

The product wins not by having the longest feature list, but by being the finance app a user can actually trust with real imported data.

**One-sentence filter for roadmap decisions:**
> Does this feature improve the trust, reviewability, or usefulness of imported financial data? If yes, it belongs early. If not, it's later-stage polish.

---

## What's Already Built (as of March 17, 2026)

### Core Infrastructure
- FastAPI + PostgreSQL backend, Docker Compose on acerserver
- SimpleFIN sync (daily 6AM + startup + manual trigger)
- Git repo on GitHub (ratpackcp7/finance-hub-v2)
- PG backup with 7-day rotation
- household_id column on all 7 tables (schema prep, no query changes yet)

### Transaction & Categorization Pipeline
- Transaction list with filtering (date, account, category, search)
- Payee rules engine: auto-apply on sync, match both description + payee fields, dedup on insert, retroactive apply on rule creation
- AI-assisted categorization via OpenRouter (Gemini Flash Lite) — in-app button with review/approve flow
- Category management (create, rename, delete)
- 12 account types (checking, savings, credit, investment, retirement, 529, UTMA, HSA, brokerage, loan, mortgage, other)

### Import Integrity (P0 — deployed March 17, 2026)
- Import batch tracking: each sync creates a batch record with full raw SimpleFIN JSON
- Near-duplicate detection: same account + amount +/-$0.02 + date +/-1 day flags for review
- import_batch_id on every new transaction for provenance
- Dupe review UI: side-by-side comparison cards with keep/remove actions
- Batch history table with status, counts, error display

### Analytics & Reporting
- Spending charts by category, payee, and trend
- Month-over-month spending deltas
- Subscription/recurring charge detector
- Sankey diagram (spending flow)
- Drill-down stat boxes (clickable)
- Net worth endpoint
- Net worth snapshots (balance_snapshots table, daily after sync)

### UI & Access
- Mobile-first responsive UI with bottom nav (SVG icons)
- Rich transaction detail modal
- PWA manifest (installable)
- Feedback button with local Postgres storage

### Not Yet Built (from original P1 list)
- Manual transaction entry
- Split transactions
- Bulk edit tools
- Tags/labels
- CSV import

---

## Priority Framework

The original plan prioritized by **user-visible features** (manual entry, splits, net worth). The revised framework prioritizes by **data trust** — because in a finance product, trust IS the product. If the ledger can't be trusted, dashboards and reports are decorative.

### Priority Tiers

| Tier | Focus | Principle |
|------|-------|-----------|
| **P0 — Import Integrity** | Make incoming data safe, repeatable, explainable | System boundary between external financial data and internal ledger |
| **P1 — Ledger Trust** | Make balances, transfers, and edits trustworthy over time | Can the user rely on this for real financial decisions? |
| **P2 — Categorization Efficiency** | Reduce manual cleanup cost, preserve user control | Rules and categorization only work well on stable data |
| **P3 — Reporting & Planning** | Turn trusted records into decision support | Reports only matter if underlying data is correct |
| **P4 — Convenience & Polish** | Speed, accessibility, product feel | Usability improvements that don't change the core trust model |

---

## Phase 0 — Import Integrity

**Goal:** Ensure incoming data is safe, repeatable, and explainable.

**Status:** Core items deployed. Remaining: pending/posted handling, CSV import, review queue.

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| Idempotent imports | ✅ Done | SimpleFIN ID-based dedup + near-dupe detection |
| Duplicate detection + review tools | ✅ Done | Side-by-side dupe review UI with keep/remove actions |
| Import batch tracking | ✅ Done | Each sync gets a batch record with stats |
| Raw import preservation | ✅ Done | Full SimpleFIN JSON stored per batch |
| Source-aware import pipeline | ✅ Done | import_batch_id on every transaction |
| Pending vs posted transaction handling | ❌ Not built | Model separately so pending charges don't skew balances |
| CSV import with saved column mappings | ❌ Not built | For institutions SimpleFIN doesn't cover (Ford Credit, Toyota Financial) |
| Merchant/payee normalization pipeline | 🟡 Partial | Payee rules exist but no systematic normalization |
| Review queue for uncategorized/low-confidence | 🟡 Partial | AI categorize button exists but no dedicated triage view |

---

## Phase 1 — Ledger Trust

**Goal:** Ensure balances, transfers, and edits can be trusted over time.

**Status:** Running balances and transfer detection deployed. Missing: reconciliation, balance checkpoints, edit history, transaction states.

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| Running account balances | ✅ Done | CTE window function, displayed per-account |
| Transfer matching with manual override | ✅ Done | Auto-detect + is_transfer flag + spending exclusion |
| Cleared / posted / reconciled transaction states | ❌ Not built | State machine for transaction lifecycle |
| Reconciliation workflow | ❌ Not built | Compare app balance vs statement balance, surface discrepancies |
| Balance checkpoints / statement anchors | ❌ Not built | User enters known statement balance to anchor accuracy |
| Edit history for transaction changes | ❌ Not built | Log what changed, when, by whom (user vs rule vs AI) |
| Data provenance at transaction level | ✅ Done | import_batch_id + raw JSON preserved |
| Locking behavior for reconciled periods | ❌ Not built | Prevent accidental edits to already-reconciled months |
| Manual transaction entry | ❌ Not built | Date, payee, amount, category, account form |

---

## Phase 2 — Categorization & Editing Efficiency

**Goal:** Reduce manual cleanup cost while preserving user control.

**Status:** Payee rules and AI categorize are built and working. Missing: advanced rule engine, bulk edit, splits, tags.

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| Advanced rules engine (multi-condition, priority ordering) | ❌ Not built | Need amount ranges, date filters, merchant + amount combos |
| Rule preview / simulation | ❌ Not built | "If I apply this rule, what would change?" |
| Bulk edit tools | ❌ Not built | Select multiple transactions, batch-apply category/tag |
| Split transactions | ❌ Not built | Single transaction to multiple category allocations |
| Tags / labels | ❌ Not built | Orthogonal to categories (vacation, tax-deductible, reimbursable) |
| Rename / merge merchant tools | ❌ Not built | Consolidate messy payee names across imports |
| Retroactive rule application | ✅ Done | Already applies rules retroactively on creation |
| Search, filters, and saved views | 🟡 Partial | Basic filters exist; no saved/bookmarked filter sets |
| Category confidence indicators | ❌ Not built | Show when AI assigned vs user vs rule |

---

## Phase 3 — Reporting & Planning

**Goal:** Turn trusted financial records into useful decision support.

**Status:** Spending charts, MoM deltas, Sankey, subscription detection, drill-down stats built. Missing: budgets UI, forecasting, net worth history chart, cash flow, goals.

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| Budget targets (monthly per category) | 🟡 Schema only | Budget table exists; no progress bars or tracking UI |
| Net worth over time | 🟡 In Progress | Snapshots collecting; chart appears after 2+ data points |
| Cash flow reporting | ❌ Not built | Income vs expenses over time with trend |
| Period-over-period comparisons (YoY, MoM) | 🟡 Partial | MoM deltas exist; no YoY or arbitrary period compare |
| Forecasting | ❌ Not built | Project future spending based on historical patterns |
| Goal tracking | ❌ Not built | Savings targets, debt payoff milestones |
| Scheduled / recurring transactions | ❌ Not built | Known future charges for cash flow projection |
| Monthly digest / summary email | ❌ Not built | Push summary to email or Telegram |

---

## Phase 4 — Convenience & Polish

| Feature | Status | Notes |
|---------|--------|-------|
| Keyboard shortcuts | ❌ | Quick nav, quick categorize |
| PWA full support | 🟡 Partial | Manifest exists; needs offline caching, push notifications |
| Attachments (receipts, statements) | ❌ | Upload and link to transactions |
| Custom category icons / emoji | ❌ | Visual flair |
| Mobile optimizations | ✅ Done | Mobile-first UI with responsive bottom nav |
| Notification center | ❌ | Alerts for large charges, sync failures, budget overspend |
| Multi-user support | 🟡 Schema only | household_id on all tables; no auth/switching yet |
| Finance Hub via cp7.dev tunnel | ❌ | Access from anywhere via Cloudflare Zero Trust |
| Debt payoff planner | ❌ | Snowball/avalanche calculator |

---

## Must-Build-Before-Scale Checklist

### Data Integrity
- [x] Imports are idempotent
- [x] Duplicate handling is explicit and reviewable
- [ ] Pending and posted transactions are modeled separately
- [x] Each transaction records its source and import batch
- [x] Raw imported values can be inspected for debugging
- [ ] Manual edits do not destroy provenance

### Ledger Trust
- [x] Account balances can be recomputed deterministically
- [x] Transfers can be matched and corrected manually
- [ ] Reconciliation exists as a real workflow, not just a flag
- [ ] Reconciled periods can be locked or protected
- [ ] Statement or checkpoint balances can anchor accuracy
- [ ] Corrections and adjustments are distinguishable from imported data

### Review Workflow
- [ ] New transactions can be triaged quickly
- [ ] Problematic transactions surface in a review queue
- [ ] Low-confidence categorizations are clearly marked
- [ ] Bulk review actions are supported
- [ ] Users can filter by account, source, date, import batch, and confidence

### Auditability
- [ ] Transaction edits are logged
- [x] Import jobs are logged
- [ ] Rule changes are logged
- [ ] Users can explain why a transaction looks the way it does

### Operational Safety
- [x] Backups are easy and tested (PG backup w/ 7-day rotation)
- [x] Export is complete enough to leave the product safely (CSV export)
- [ ] Sync failures are visible (partially — sync_log exists, no push alerts)
- [x] Secret handling is isolated from app logic (Docker secrets)

---

## Next Actions (Recommended Build Order)

1. ~~Import dedup + batch tracking~~ ✅ Done
2. CSV import with column mapping — Chase/Discover formats first, save mappings per institution
3. Reconciliation workflow — statement balance entry, surface discrepancies
4. Manual transaction entry — date, payee, amount, category, account form
5. Split transactions — one txn to multiple category allocations
6. Advanced rules engine — multi-condition, priority ordering, preview mode

---

## What Moved and Why

### Moved UP (more important than original plan suggested)
| Feature | Was | Now | Reason |
|---------|-----|-----|--------|
| Import dedup / idempotency | Not planned | P0 ✅ | Without this, re-syncs create phantom transactions |
| Import batch tracking | Not planned | P0 ✅ | Can't debug or rollback bad imports |
| Raw import preservation | Not planned | P0 ✅ | Lose ability to explain data discrepancies |
| Reconciliation | Vaguely P2 | P1 | Core trust feature — without it, balances are aspirational |
| Transfer matching | Not planned | P1 ✅ | Internal transfers double-count in spending without this |
| Edit history / provenance | Not planned | P1 | Can't explain why a transaction looks the way it does |
| Balance checkpoints | Not planned | P1 | Statement anchors catch drift before it compounds |
| CSV import | P2 | P0 | Import-first product needs multi-source from the start |

### Moved DOWN (useful but shouldn't outrank trust systems)
| Feature | Was | Now | Reason |
|---------|-----|-----|--------|
| Keyboard shortcuts | P3 | P4 | Nice UX, zero trust impact |
| PWA full support | P3 | P4 | Manifest exists; full offline can wait |
| Category emoji | P3 | P4 | Cosmetic |
| Debt payoff planner | P2 | P4 | Planning tool that needs trusted data first |

---

*This document replaces the original Feature Benchmark & Gap Analysis. Updated to reflect trust-first prioritization, current build state, and P0 completion as of March 17, 2026.*
