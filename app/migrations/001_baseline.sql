-- Baseline migration: captures all schema as of v4.0.0
-- All statements are idempotent (IF NOT EXISTS / IF EXISTS)

-- ── Core tables (created by initial setup, not managed here) ──
-- accounts, transactions, categories, payee_rules, sync_log
-- These are assumed to exist from the original schema.

-- ── Transfer flag ──
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_transfer BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_txn_transfer ON transactions(is_transfer) WHERE is_transfer = TRUE;

-- ── Budgets ──
CREATE TABLE IF NOT EXISTS budgets (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    monthly_amount NUMERIC(15,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(category_id)
);

-- ── Account types ──
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS account_type TEXT DEFAULT 'checking';

-- ── Feedback ──
CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'feature',
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    notion_page_id TEXT DEFAULT NULL
);

-- ── Balance snapshots ──
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    account_id TEXT NOT NULL,
    account_name TEXT,
    account_type TEXT,
    balance NUMERIC(15,2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(snapshot_date, account_id)
);
CREATE INDEX IF NOT EXISTS idx_snap_date ON balance_snapshots(snapshot_date);

-- ── Cleanup: drop deprecated household_id ──
ALTER TABLE accounts DROP COLUMN IF EXISTS household_id;
ALTER TABLE transactions DROP COLUMN IF EXISTS household_id;
ALTER TABLE categories DROP COLUMN IF EXISTS household_id;
ALTER TABLE payee_rules DROP COLUMN IF EXISTS household_id;
ALTER TABLE budgets DROP COLUMN IF EXISTS household_id;
ALTER TABLE feedback DROP COLUMN IF EXISTS household_id;
ALTER TABLE balance_snapshots DROP COLUMN IF EXISTS household_id;
DROP INDEX IF EXISTS idx_acct_household;
DROP INDEX IF EXISTS idx_txn_household;
DROP INDEX IF EXISTS idx_cat_household;
DROP INDEX IF EXISTS idx_rules_household;

-- ── Import batch tracking ──
CREATE TABLE IF NOT EXISTS import_batches (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    source TEXT NOT NULL DEFAULT 'simplefin',
    raw_payload JSONB,
    accounts_seen INT DEFAULT 0,
    txns_added INT DEFAULT 0,
    txns_updated INT DEFAULT 0,
    txns_skipped INT DEFAULT 0,
    dupes_flagged INT DEFAULT 0,
    error_message TEXT
);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS import_batch_id INT;
CREATE INDEX IF NOT EXISTS idx_txn_batch ON transactions(import_batch_id);

-- ── Duplicate flags ──
CREATE TABLE IF NOT EXISTS duplicate_flags (
    id SERIAL PRIMARY KEY,
    txn_id TEXT NOT NULL,
    duplicate_of TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    batch_id INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dupe_status ON duplicate_flags(status);
CREATE INDEX IF NOT EXISTS idx_dupe_batch ON duplicate_flags(batch_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dupe_pair ON duplicate_flags(txn_id, duplicate_of);

-- ── Audit log (append-only) ──
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

-- ── Soft delete columns ──
ALTER TABLE categories ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE payee_rules ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE budgets ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
