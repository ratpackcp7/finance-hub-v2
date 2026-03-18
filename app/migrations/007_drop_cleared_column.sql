-- transactions.cleared replaced by reconciliation_session_items
ALTER TABLE transactions DROP COLUMN IF EXISTS cleared;
