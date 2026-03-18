-- 003: CSV import mappings table
CREATE TABLE IF NOT EXISTS csv_mappings (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,           -- e.g. "Chase Credit Card", "Discover CC"
    institution TEXT,                     -- e.g. "chase", "discover", "citi"
    header_signature TEXT NOT NULL,       -- comma-joined lowercase headers for auto-detect
    mapping JSONB NOT NULL,              -- {date_col, amount_col, description_col, ...}
    sign_flip BOOLEAN DEFAULT FALSE,     -- flip amount sign (some banks use opposite convention)
    date_format TEXT DEFAULT 'MM/DD/YYYY',
    notes TEXT,
    is_preset BOOLEAN DEFAULT FALSE,     -- true for built-in presets
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Built-in presets
INSERT INTO csv_mappings (name, institution, header_signature, mapping, sign_flip, date_format, is_preset, notes)
VALUES
    ('Chase Credit Card', 'chase',
     'transaction date,post date,description,category,type,amount',
     '{"date_col": "Transaction Date", "post_date_col": "Post Date", "description_col": "Description", "amount_col": "Amount", "category_col": "Category", "type_col": "Type"}',
     FALSE, 'MM/DD/YYYY', TRUE,
     'Charges positive, payments/credits negative.'),

    ('Chase Checking', 'chase',
     'details,posting date,description,amount,type,balance,check or slip #',
     '{"date_col": "Posting Date", "description_col": "Description", "amount_col": "Amount", "type_col": "Type", "balance_col": "Balance"}',
     FALSE, 'MM/DD/YYYY', TRUE,
     'Withdrawals negative, deposits positive.'),

    ('Discover Credit Card', 'discover',
     'trans. date,post date,description,amount,category',
     '{"date_col": "Trans. Date", "post_date_col": "Post Date", "description_col": "Description", "amount_col": "Amount", "category_col": "Category"}',
     TRUE, 'MM/DD/YYYY', TRUE,
     'Discover uses debits=positive, credits=negative. sign_flip inverts to match FH convention (expenses negative).'),

    ('Citi Double Cash', 'citi',
     'status,date,description,debit,credit',
     '{"date_col": "Date", "description_col": "Description", "debit_col": "Debit", "credit_col": "Credit", "status_col": "Status"}',
     FALSE, 'MM/DD/YYYY', TRUE,
     'Two amount columns. Debit=charges (stored as negative), Credit=payments (stored as positive).')
ON CONFLICT (name) DO NOTHING;
