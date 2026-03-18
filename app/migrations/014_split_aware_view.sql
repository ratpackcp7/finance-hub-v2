-- Migration 014: Split-aware spending view + tag filtering support
-- All statements idempotent

-- ══════════════════════════════════════════════
-- SPLIT-AWARE SPENDING VIEW
-- ══════════════════════════════════════════════
-- Union of:
--   1. Non-split transactions (normal, use txn category)
--   2. Split rows (replace parent with per-split category + amount)
-- Used by spending endpoints for correct category breakdowns.

CREATE OR REPLACE VIEW spending_items AS
-- Non-split transactions
SELECT
    t.id AS txn_id,
    t.account_id,
    t.posted,
    t.amount,
    t.description,
    t.payee,
    t.category_id,
    t.is_transfer,
    t.pending,
    t.recurring,
    t.has_splits,
    NULL::integer AS split_id
FROM transactions t
WHERE COALESCE(t.has_splits, FALSE) = FALSE

UNION ALL

-- Split rows (replace parent amount + category)
SELECT
    t.id AS txn_id,
    t.account_id,
    t.posted,
    s.amount,
    COALESCE(s.description, t.description) AS description,
    t.payee,
    s.category_id,
    t.is_transfer,
    t.pending,
    t.recurring,
    TRUE AS has_splits,
    s.id AS split_id
FROM transactions t
JOIN transaction_splits s ON s.txn_id = t.id
WHERE t.has_splits = TRUE;
