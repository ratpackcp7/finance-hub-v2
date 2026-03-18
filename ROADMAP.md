# Finance Hub v2 — Product Roadmap

*Updated March 18, 2026 (v4.6.0+). Reflects full build state after Phase 1 MVP, Phase 2 Automation, Phase 3 Wealth, and Operations batch.*

---

## Product Thesis

Finance Hub is an import-first, self-hosted finance app designed for high-trust transaction review, strong normalization and rules, reliable balance tracking, and optional AI assistance that improves workflow without becoming a hidden source of truth.

**One-sentence filter for roadmap decisions:**
> Does this feature improve the trust, reviewability, or usefulness of imported financial data? If yes, it belongs early. If not, it's later-stage polish.

---

## Current Stats (v4.6.0+)

- 27 JS files, 17 migrations, 26 routers, ~119 API endpoints
- 17 pages, 14+ modals
- 26 database tables
- 3 Docker containers (app, worker, postgres)
- SimpleFIN sync: 6AM + 6PM CT + startup + manual
- Accessible at finance.cp7.dev via Cloudflare Zero Trust tunnel
- Telegram monthly digest: 1st of each month at 9AM CT

---

## What's Built

### Phase 0 — Import Integrity ✅ Complete

| Feature | Status | Notes |
|---------|--------|-------|
| Idempotent imports | ✅ | SimpleFIN ID-based dedup + near-dupe detection |
| Duplicate detection + review | ✅ | Side-by-side dupe review UI, keep/remove actions |
| Import batch tracking | ✅ | Each sync creates batch with full raw JSON |
| Raw import preservation | ✅ | Raw payload + per-txn JSON, 90-day retention purge |
| Source tracking | ✅ | `source` field: sync/csv/manual on all transactions |
| CSV import | ✅ | 6 presets (Chase CC, Chase Checking, Discover, Citi, Ford Credit, Toyota Financial), auto-detect by headers, custom mappings |
| Pending transaction handling | ✅ | Pending flag from SimpleFIN, ⏳ badge, excluded from spending |
| Review queue | ✅ | Priority-sorted: uncategorized > AI > recent > large. Filter toggles, mark-reviewed, batch clear |

### Phase 1 — Ledger Trust ✅ Complete

| Feature | Status | Notes |
|---------|--------|-------|
| Running account balances | ✅ | CTE window function per account |
| Transfer pair linking | ✅ | Auto-detect + `transfer_pair_id` linking both sides |
| Reconciliation workflow | ✅ | Sessions (create/clear/complete/abandon), statement balance, cleared counts |
| Reconciliation period locking | ✅ | PATCH/split guards reject edits on reconciled txns, unlock endpoint |
| Manual transaction entry | ✅ | Full modal: account, date, type, amount, payee, description, category, notes, transfer. Delete for manual-only. |
| Balance history | ✅ | Daily snapshots (worker), net worth history chart |
| Edit history / audit | ✅ | audit_log tracks category, payee, notes, transfer, manual create/delete, reconcile, tags |
| Data provenance | ✅ | import_batch_id + first_import_batch_id + last_seen_batch_id + source field + category_source |

### Phase 2 — Categorization & Editing ✅ ~90% Complete

| Feature | Status | Notes |
|---------|--------|-------|
| Payee rules engine | ✅ | Pattern match on description + payee, retroactive apply, 176 rules |
| Advanced rules (multi-condition) | ✅ | Amount min/max, set_transfer action, tag action, priority ordering |
| Rule preview / simulation | ✅ | "Test a Pattern" card on Rules page, inline preview in create modal with debounce |
| AI-assisted categorization | ✅ | OpenRouter (Gemini Flash Lite), in-app review/approve |
| Split transactions | ✅ | One txn → multiple category allocations, ✂ badge, amounts must balance |
| Tags / labels | ✅ | 6 seeded tags, CRUD, checkbox toggles in edit modal, tag filter on transactions |
| Split-aware spending | ✅ | `spending_items` VIEW, 8 queries use it (by-category, deltas, flow, trends, budgets) |
| Category confidence indicators | ✅ | `category_source` field: user/rule/ai/sync. Badges on transactions. |
| Bulk edit tools | ✅ | Select multiple → batch category/tag (bulk.py + bulk.js) |
| Rename / merge merchants | ✅ | Consolidate messy payee names (merchants.py + merchants.js) |
| Saved filter views | ❌ | Bookmark a filter combo |

### Phase 3 — Reporting & Planning ✅ ~95% Complete

| Feature | Status | Notes |
|---------|--------|-------|
| Budget targets + progress | ✅ | Monthly per category, dashboard progress bars, budget vs actual chart |
| Net worth dashboard | ✅ | NW trend chart (1M/3M/6M/12M/YTD), NW breakdown pie, asset/liability groups |
| Cash flow reporting | ✅ | Surplus/deficit bar chart, income vs expenses table, savings rate bars |
| Spending analytics | ✅ | By category, by payee, MoM deltas, trends, Sankey flow diagram |
| Subscription detection | ✅ | Auto-detect monthly recurring, annual cost estimate |
| Upcoming bills | ✅ | Account due dates + recurring prediction, urgency coloring, autopay badges |
| Debt payoff calculator | ✅ | Snowball/avalanche, extra payment modeling, months-saved comparison |
| Savings goals | ✅ | CRUD, account-linked auto-track, manual contributions, progress bars, dashboard widget |
| Telegram monthly digest | ✅ | Income/spending/net/savings rate/top categories/budget status/net worth. Worker cron 1st @ 9AM CT. |
| Investment tracking | ✅ | Holdings table, yfinance price refresh, Vanguard performance CSV, portfolio value chart |
| Dividend tracking | ✅ | Monthly aggregates + by-holding breakdown + annual estimate from investment transactions |
| Period comparison (MoM) | ✅ | Month-over-month comparison (compare.py + compare.js) |
| Forecasting | ✅ | Cashflow projection (N months), per-category pace-based forecast, what-if scenarios (forecast.py + forecast.js) |

### Phase 4 — Wealth ✅ ~90% Complete

| Feature | Status | Notes |
|---------|--------|-------|
| Broker/portfolio imports | ✅ | Holdings table, Vanguard performance CSV import, yfinance price refresh |
| Investment transactions | ✅ | Buy/sell/dividend/reinvest/fee/split/transfer CRUD (inv_txns.py) |
| Tax lot tracking (FIFO) | ✅ | Auto-create lots on buy, FIFO close on sell, open/closed lot views, cost basis per share |
| Realized gain/loss | ✅ | Long-term vs short-term classification, per-holding + total summary (/gains endpoint) |
| Unrealized gain/loss | ✅ | Market value vs cost basis across all holdings, percentage return |
| Benchmark analytics | ✅ | Compare portfolio returns against SPY/VTI/QQQ, alpha calculation, auto-fetch via yfinance, manual refresh |
| Per-holding dividend history | 🟡 | Monthly aggregates exist. No discrete dividend event model (ex-date, pay-date, per-share amount). |
| YoY comparison | ❌ | MoM exists. No YoY or arbitrary period-over-period. |

### Phase 5 — Convenience & Polish

| Feature | Status | Notes |
|---------|--------|-------|
| Mobile-first responsive UI | ✅ | Bottom nav, card layouts, touch-friendly |
| PWA manifest | ✅ | Installable. No offline caching. |
| Account detail modal | ✅ | CC: due day, APR, min payment, credit limit, utilization bar, autopay. Loans: rate, term, payment, maturity. |
| Source badges | ✅ | ✎ manual, ⬆ csv, ⏳ pending, 🔒 reconciled, ✂ split, ↻ recurring, ↔ transfer |
| finance.cp7.dev tunnel | ✅ | Cloudflare Zero Trust, 302 auth |
| Cache busters | ✅ | All 27 JS files have ?v= timestamps |
| Keyboard shortcuts | ❌ | Quick nav, quick categorize |
| Attachments (receipts) | ❌ | Upload + link to transactions |
| Multi-user support | 🟡 | household_id columns exist, no auth |
| Notification center | ❌ | In-app alerts |

---

## Must-Build-Before-Scale Checklist

### Data Integrity
- [x] Imports are idempotent
- [x] Duplicate handling is explicit and reviewable
- [x] Pending and posted transactions modeled
- [x] Each transaction records its source and import batch
- [x] Raw imported values can be inspected for debugging
- [x] Manual edits tracked in audit log

### Ledger Trust
- [x] Account balances can be recomputed deterministically
- [x] Transfers can be matched and corrected manually
- [x] Reconciliation exists as a real workflow
- [x] Reconciled periods can be locked
- [x] Statement balances anchor accuracy
- [x] Corrections distinguishable from imported data (category_source)

### Review Workflow
- [x] New transactions can be triaged quickly (Review page)
- [x] Problematic transactions surface in review queue
- [x] Low-confidence categorizations clearly marked
- [x] Bulk review actions supported (mark-all-reviewed)
- [x] Filter by account, source, date, category, tag

### Auditability
- [x] Transaction edits are logged
- [x] Import jobs are logged
- [x] Rule changes are logged (retroactive apply count)
- [x] Users can explain why a transaction looks the way it does

### Operational Safety
- [x] Backups are easy and tested (PG backup w/ 7-day rotation)
- [x] Export complete enough to leave safely (CSV export)
- [x] Sync results visible (sync_log, batch history, dashboard)
- [x] Secret handling isolated (Docker secrets)
- [x] Monthly digest to Telegram

---

## Remaining Priorities

### High Impact
1. **YoY / arbitrary period comparison** — extend compare.py beyond MoM to support any two date ranges
2. **Saved filter views** — bookmark a filter combo for quick recall on transactions page

### Medium Impact
3. **Per-holding dividend event model** — discrete dividend events with ex-date, pay-date, per-share amount (beyond current monthly aggregates)
4. **Multi-user auth** — household_id wiring + login

### Lower Priority
5. **Keyboard shortcuts** — quick nav, quick categorize
6. **Receipt attachments** — upload + link to transactions
7. **PWA offline** — service worker + offline caching
8. **Notification center** — in-app alerts

---

*26 routers, ~119 endpoints, 27 JS files, 17 migrations, 26 tables, 17 pages. Finance Hub is a functional personal finance platform.*
