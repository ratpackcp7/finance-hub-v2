-- Migration 009: Holdings table for portfolio tracking
CREATE TABLE IF NOT EXISTS holdings (
    id SERIAL PRIMARY KEY,
    account_id TEXT REFERENCES accounts(id),
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    shares NUMERIC(15,6) NOT NULL DEFAULT 0,
    cost_basis NUMERIC(15,2),
    last_price NUMERIC(15,4),
    last_price_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(account_id, ticker)
);

CREATE TABLE IF NOT EXISTS holding_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    holding_id INTEGER REFERENCES holdings(id) ON DELETE CASCADE,
    price NUMERIC(15,4),
    market_value NUMERIC(15,2),
    UNIQUE(snapshot_date, holding_id)
);
