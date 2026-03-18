-- Migration 016: Review workflow + data hygiene
-- All statements idempotent

-- ══════════════════════════════════════════════
-- REVIEW WORKFLOW
-- ══════════════════════════════════════════════
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_txn_reviewed ON transactions(reviewed_at) WHERE reviewed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_txn_cat_source ON transactions(category_source);

-- ══════════════════════════════════════════════
-- DATA HYGIENE: Backfill category_source nulls
-- ══════════════════════════════════════════════
UPDATE transactions SET category_source = 'user'
WHERE category_source IS NULL AND category_manual = TRUE;

UPDATE transactions SET category_source = 'sync'
WHERE category_source IS NULL;
