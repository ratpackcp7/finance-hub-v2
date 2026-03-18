-- Migration 013: Advanced rules, upcoming bills view support
-- All statements idempotent

-- ══════════════════════════════════════════════
-- ADVANCED RULES ENGINE
-- ══════════════════════════════════════════════
-- Add amount range conditions + tag action + transfer action
ALTER TABLE payee_rules ADD COLUMN IF NOT EXISTS amount_min NUMERIC(15,2);
ALTER TABLE payee_rules ADD COLUMN IF NOT EXISTS amount_max NUMERIC(15,2);
ALTER TABLE payee_rules ADD COLUMN IF NOT EXISTS set_transfer BOOLEAN;     -- NULL=don't change, TRUE=mark transfer, FALSE=unmark
ALTER TABLE payee_rules ADD COLUMN IF NOT EXISTS tag_id INTEGER REFERENCES tags(id) ON DELETE SET NULL;
ALTER TABLE payee_rules ADD COLUMN IF NOT EXISTS description TEXT;          -- human-readable note about what this rule does

-- ══════════════════════════════════════════════
-- UPCOMING BILLS
-- ══════════════════════════════════════════════
-- We'll compute upcoming bills from recurring transactions + account due dates.
-- No new table needed — it's a computed view from existing data.
-- But let's add a next_due_date on accounts for manual override.
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS next_due_date DATE;
