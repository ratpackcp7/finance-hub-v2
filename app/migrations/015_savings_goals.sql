-- Migration 015: Savings goals
-- All statements idempotent

CREATE TABLE IF NOT EXISTS savings_goals (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    target_amount NUMERIC(15,2) NOT NULL,
    current_amount NUMERIC(15,2) DEFAULT 0,
    -- Optional: link to account(s) whose balance tracks progress automatically
    account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    -- Goal type: emergency_fund, savings, debt_payoff, purchase, custom
    goal_type TEXT NOT NULL DEFAULT 'savings',
    -- Target date (optional)
    target_date DATE,
    -- Monthly contribution target
    monthly_contribution NUMERIC(15,2),
    -- Color for UI
    color TEXT DEFAULT '#3b82f6',
    -- Notes
    notes TEXT,
    -- Status
    status TEXT NOT NULL DEFAULT 'active',  -- active, completed, paused
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Goal history snapshots (track progress over time)
CREATE TABLE IF NOT EXISTS goal_snapshots (
    id SERIAL PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    amount NUMERIC(15,2) NOT NULL,
    UNIQUE(goal_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_goal_snap_date ON goal_snapshots(snapshot_date);
