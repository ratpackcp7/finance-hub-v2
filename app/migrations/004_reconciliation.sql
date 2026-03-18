-- 004: Reconciliation workflow
-- Transaction cleared/reconciled state
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS cleared BOOLEAN DEFAULT FALSE;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS reconciled_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_txn_cleared ON transactions(cleared) WHERE cleared = TRUE;

-- Reconciliation sessions
CREATE TABLE IF NOT EXISTS reconciliation_sessions (
    id SERIAL PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    statement_date DATE NOT NULL,
    statement_balance NUMERIC(15,2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',  -- open, completed, abandoned
    cleared_count INT DEFAULT 0,
    cleared_balance NUMERIC(15,2) DEFAULT 0,
    difference NUMERIC(15,2) DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_recon_account ON reconciliation_sessions(account_id);
CREATE INDEX IF NOT EXISTS idx_recon_status ON reconciliation_sessions(status);
