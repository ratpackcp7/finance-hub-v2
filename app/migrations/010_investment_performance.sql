-- Migration 010: Investment performance history (monthly Vanguard data)
CREATE TABLE IF NOT EXISTS investment_performance (
    id SERIAL PRIMARY KEY,
    month DATE NOT NULL,
    beginning_balance NUMERIC(15,2),
    deposits_withdrawals NUMERIC(15,2),
    market_gain_loss NUMERIC(15,2),
    income_returns NUMERIC(15,2),
    personal_investment_returns NUMERIC(15,2),
    cumulative_returns NUMERIC(15,2),
    ending_balance NUMERIC(15,2),
    source TEXT DEFAULT 'vanguard',
    UNIQUE(month, source)
);
