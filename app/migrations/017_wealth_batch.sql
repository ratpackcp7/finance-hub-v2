-- Migration 017: Wealth batch — investment transactions, benchmark prices, tax lots
-- All statements idempotent

-- ══════════════════════════════════════════════
-- INVESTMENT TRANSACTIONS
-- ══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS investment_transactions (
    id SERIAL PRIMARY KEY,
    holding_id INTEGER REFERENCES holdings(id) ON DELETE CASCADE,
    account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
    txn_type TEXT NOT NULL,  -- buy, sell, dividend, reinvest, fee, split, transfer_in, transfer_out
    txn_date DATE NOT NULL,
    shares NUMERIC(15,6),
    price_per_share NUMERIC(15,4),
    total_amount NUMERIC(15,2) NOT NULL,
    fees NUMERIC(15,2) DEFAULT 0,
    notes TEXT,
    source TEXT DEFAULT 'manual',  -- manual, csv, sync
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inv_txn_holding ON investment_transactions(holding_id);
CREATE INDEX IF NOT EXISTS idx_inv_txn_date ON investment_transactions(txn_date DESC);
CREATE INDEX IF NOT EXISTS idx_inv_txn_type ON investment_transactions(txn_type);

-- ══════════════════════════════════════════════
-- BENCHMARK PRICES (daily cache for comparison)
-- ══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS benchmark_prices (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,       -- SPY, VTI, QQQ
    price_date DATE NOT NULL,
    close_price NUMERIC(15,4) NOT NULL,
    UNIQUE(ticker, price_date)
);
CREATE INDEX IF NOT EXISTS idx_bench_ticker_date ON benchmark_prices(ticker, price_date);

-- ══════════════════════════════════════════════
-- TAX LOTS
-- ══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS tax_lots (
    id SERIAL PRIMARY KEY,
    holding_id INTEGER NOT NULL REFERENCES holdings(id) ON DELETE CASCADE,
    inv_txn_id INTEGER REFERENCES investment_transactions(id),  -- the buy that opened this lot
    open_date DATE NOT NULL,
    shares_purchased NUMERIC(15,6) NOT NULL,
    cost_basis_per_share NUMERIC(15,4) NOT NULL,
    shares_remaining NUMERIC(15,6) NOT NULL,
    basis_remaining NUMERIC(15,2) NOT NULL,
    closed_date DATE,
    close_price NUMERIC(15,4),
    realized_gain NUMERIC(15,2),
    is_long_term BOOLEAN,       -- held > 1 year at close
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lot_holding ON tax_lots(holding_id);
CREATE INDEX IF NOT EXISTS idx_lot_open ON tax_lots(shares_remaining) WHERE shares_remaining > 0;
