-- Session-scoped reconciliation: cleared state per session instead of global transactions.cleared
CREATE TABLE IF NOT EXISTS reconciliation_session_items (
    session_id INT NOT NULL REFERENCES reconciliation_sessions(id) ON DELETE CASCADE,
    txn_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    cleared BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (session_id, txn_id)
);

CREATE INDEX IF NOT EXISTS idx_recon_items_session ON reconciliation_session_items(session_id);
CREATE INDEX IF NOT EXISTS idx_recon_items_txn ON reconciliation_session_items(txn_id);

-- Enforce one open session per account at the DB level
CREATE UNIQUE INDEX IF NOT EXISTS uq_recon_open_session_per_account
ON reconciliation_sessions(account_id)
WHERE status = 'open';
