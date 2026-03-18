-- Migration 012: Split transactions, tags, Ford/Toyota CSV presets
-- All statements idempotent

-- ══════════════════════════════════════════════
-- SPLIT TRANSACTIONS
-- ══════════════════════════════════════════════
-- A parent txn can be split across multiple categories.
-- Splits must sum to the parent's amount.
-- When splits exist, spending queries use splits instead of the parent's category.

CREATE TABLE IF NOT EXISTS transaction_splits (
    id SERIAL PRIMARY KEY,
    txn_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    amount NUMERIC(15,2) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_split_txn ON transaction_splits(txn_id);

-- Flag on parent transaction indicating it has splits
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS has_splits BOOLEAN DEFAULT FALSE;

-- ══════════════════════════════════════════════
-- TAGS
-- ══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#64748b',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transaction_tags (
    txn_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (txn_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_tt_tag ON transaction_tags(tag_id);

-- Seed common tags
INSERT INTO tags (name, color) VALUES
    ('Tax Deductible', '#22c55e'),
    ('Reimbursable', '#3b82f6'),
    ('Vacation', '#a855f7'),
    ('Business', '#f59e0b'),
    ('Gift', '#ec4899'),
    ('One-Time', '#64748b')
ON CONFLICT (name) DO NOTHING;

-- ══════════════════════════════════════════════
-- FORD / TOYOTA CSV PRESETS
-- ══════════════════════════════════════════════
-- Ford Credit typical export: Date, Description, Amount
INSERT INTO csv_mappings (name, institution, header_signature, mapping, sign_flip, date_format, is_preset, notes)
VALUES
    ('Ford Credit', 'ford',
     'date,description,amount',
     '{"date_col": "Date", "description_col": "Description", "amount_col": "Amount"}',
     FALSE, 'MM/DD/YYYY', TRUE,
     'Ford Motor Credit statement export. Payments negative, charges positive.')
ON CONFLICT (name) DO NOTHING;

-- Toyota Financial typical export: Transaction Date, Description, Amount
INSERT INTO csv_mappings (name, institution, header_signature, mapping, sign_flip, date_format, is_preset, notes)
VALUES
    ('Toyota Financial', 'toyota',
     'transaction date,description,amount',
     '{"date_col": "Transaction Date", "description_col": "Description", "amount_col": "Amount"}',
     FALSE, 'MM/DD/YYYY', TRUE,
     'Toyota Financial Services statement export.')
ON CONFLICT (name) DO NOTHING;
