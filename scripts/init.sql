-- Finance Hub v2 — PostgreSQL schema
-- SimpleFIN-native. No Plaid. Run automatically on first container start.

-- ─────────────────────────────────────────────
-- Accounts (synced from SimpleFIN)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts (
    id              TEXT PRIMARY KEY,   -- SimpleFIN account id
    name            TEXT NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    balance         NUMERIC(15,2),
    balance_date    TIMESTAMPTZ,
    org_name        TEXT,               -- institution name from SimpleFIN org block
    org_domain      TEXT,
    on_budget       BOOLEAN NOT NULL DEFAULT TRUE,
    hidden          BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- Categories (user-defined)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    color       TEXT DEFAULT '#64748b',   -- hex color for UI badges
    group_name  TEXT,                      -- optional grouping (Housing, Food, etc.)
    is_income   BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order  INTEGER DEFAULT 0
);

-- Seed with sensible defaults
INSERT INTO categories (name, color, group_name, sort_order) VALUES
    ('Groceries',       '#22c55e', 'Food',         10),
    ('Dining Out',      '#86efac', 'Food',         11),
    ('Gas',             '#f59e0b', 'Transport',    20),
    ('Auto',            '#fbbf24', 'Transport',    21),
    ('Mortgage/Rent',   '#3b82f6', 'Housing',      30),
    ('Utilities',       '#60a5fa', 'Housing',      31),
    ('Internet/Phone',  '#93c5fd', 'Housing',      32),
    ('Insurance',       '#a78bfa', 'Housing',      33),
    ('Subscriptions',   '#c084fc', 'Lifestyle',    40),
    ('Entertainment',   '#e879f9', 'Lifestyle',    41),
    ('Shopping',        '#f472b6', 'Lifestyle',    42),
    ('Health/Medical',  '#fb7185', 'Health',       50),
    ('Kids',            '#fda4af', 'Family',       60),
    ('Home Improvement','#fb923c', 'Home',         70),
    ('Savings',         '#34d399', 'Finance',      80),
    ('Credit Card Pay', '#6ee7b7', 'Finance',      81),
    ('Payroll',         '#4ade80', 'Income',       90),
    ('Other Income',    '#86efac', 'Income',       91),
    ('Uncategorized',   '#475569', NULL,           999)
ON CONFLICT (name) DO NOTHING;

-- ─────────────────────────────────────────────
-- Payee rules (auto-categorization)
-- match_pattern is a case-insensitive substring match against transaction description
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payee_rules (
    id              SERIAL PRIMARY KEY,
    match_pattern   TEXT NOT NULL,          -- e.g. 'walmart', 'shell', 'netflix'
    payee_name      TEXT,                   -- normalized display name e.g. 'Walmart'
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    priority        INTEGER DEFAULT 0,      -- higher = evaluated first
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payee_rules_pattern ON payee_rules(lower(match_pattern));

-- ─────────────────────────────────────────────
-- Transactions (synced from SimpleFIN)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    id              TEXT PRIMARY KEY,       -- SimpleFIN transaction id
    account_id      TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    posted          DATE NOT NULL,
    amount          NUMERIC(15,2) NOT NULL, -- negative = debit (SimpleFIN convention)
    description     TEXT,                   -- raw description from bank
    payee           TEXT,                   -- normalized payee (from rule or manual edit)
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    category_manual BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE = user set it, don't overwrite
    pending         BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT,
    raw             JSONB,                  -- full SimpleFIN transaction object
    inserted_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_txn_account  ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_txn_posted   ON transactions(posted DESC);
CREATE INDEX IF NOT EXISTS idx_txn_category ON transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_txn_pending  ON transactions(pending);

-- ─────────────────────────────────────────────
-- Sync log (one row per SimpleFIN pull)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_log (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          TEXT DEFAULT 'running',  -- running | ok | error
    accounts_seen   INTEGER DEFAULT 0,
    txns_added      INTEGER DEFAULT 0,
    txns_updated    INTEGER DEFAULT 0,
    error_message   TEXT
);
