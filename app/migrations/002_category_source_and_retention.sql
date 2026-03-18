-- 002: Category provenance tracking + raw payload retention
-- P2: AI categorization privacy/provenance
-- P3: Raw payload retention policy

-- ── Category source tracking ──
-- Tracks WHO set the category: user, ai, rule, sync (null = legacy/unknown)
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_source TEXT;

-- Backfill: anything with category_manual=TRUE was set by user or AI (ambiguous legacy)
-- Leave as NULL — only new categorizations get tagged going forward.

-- ── Raw payload retention ──
-- Null out raw_payload on import_batches older than retention window.
-- Keeps the batch metadata (counts, status, timestamps) forever.
CREATE OR REPLACE FUNCTION purge_old_payloads(retention_days INT DEFAULT 90)
RETURNS INT AS $$
DECLARE
    purged INT;
BEGIN
    UPDATE import_batches
    SET raw_payload = NULL
    WHERE raw_payload IS NOT NULL
      AND started_at < NOW() - (retention_days || ' days')::INTERVAL;
    GET DIAGNOSTICS purged = ROW_COUNT;
    RETURN purged;
END;
$$ LANGUAGE plpgsql;

-- Also clean up raw JSON on individual transactions after retention window
-- (the "raw" column stores per-txn SimpleFIN payload)
CREATE OR REPLACE FUNCTION purge_old_txn_raw(retention_days INT DEFAULT 90)
RETURNS INT AS $$
DECLARE
    purged INT;
BEGIN
    UPDATE transactions
    SET raw = NULL
    WHERE raw IS NOT NULL
      AND posted < CURRENT_DATE - retention_days;
    GET DIAGNOSTICS purged = ROW_COUNT;
    RETURN purged;
END;
$$ LANGUAGE plpgsql;
