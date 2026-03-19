-- B.6: category_locked — prevent automatic re-categorization of user-locked rows
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_locked BOOLEAN DEFAULT FALSE;

-- Index for efficient filtering in rule/AI categorization queries
CREATE INDEX IF NOT EXISTS idx_txn_category_locked
    ON transactions (category_locked) WHERE category_locked = TRUE;

COMMENT ON COLUMN transactions.category_locked IS
    'When TRUE, payee rules, AI categorization, and sync re-categorization will skip this row.';
