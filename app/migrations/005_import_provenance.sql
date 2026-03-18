-- Track first-seen vs last-seen import batch for auditability
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS first_import_batch_id INT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS last_seen_batch_id INT;

UPDATE transactions
SET first_import_batch_id = COALESCE(first_import_batch_id, import_batch_id),
    last_seen_batch_id   = COALESCE(last_seen_batch_id, import_batch_id)
WHERE import_batch_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_txn_first_batch ON transactions(first_import_batch_id);
CREATE INDEX IF NOT EXISTS idx_txn_last_seen_batch ON transactions(last_seen_batch_id);
