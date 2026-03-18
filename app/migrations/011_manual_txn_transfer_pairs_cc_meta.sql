-- Migration 011: Manual transactions, transfer pairs, credit card account metadata
-- Idempotent (IF NOT EXISTS / IF EXISTS)

-- ── Transfer pair linking ──
-- Replaces simple is_transfer boolean with linked pairs
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS transfer_pair_id TEXT;
CREATE INDEX IF NOT EXISTS idx_txn_transfer_pair ON transactions(transfer_pair_id) WHERE transfer_pair_id IS NOT NULL;

-- ── Manual transaction marker ──
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'sync';
-- Values: 'sync' (SimpleFIN), 'csv', 'manual'
-- Backfill existing: anything with import_batch_id that came from CSV
UPDATE transactions SET source = 'csv' WHERE source IS NULL AND import_batch_id IS NOT NULL
  AND id LIKE 'csv_%';
UPDATE transactions SET source = 'sync' WHERE source IS NULL OR source = '';

-- ── Credit card account metadata ──
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS payment_due_day INTEGER;       -- 1-31
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS minimum_payment NUMERIC(15,2);
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS apr NUMERIC(5,3);              -- e.g. 24.990
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS credit_limit NUMERIC(15,2);
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS autopay_enabled BOOLEAN DEFAULT FALSE;

-- ── Loan account metadata ──
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS loan_rate NUMERIC(6,4);        -- e.g. 5.2500
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS loan_term_months INTEGER;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS loan_payment NUMERIC(15,2);    -- scheduled monthly payment
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS loan_maturity_date DATE;
