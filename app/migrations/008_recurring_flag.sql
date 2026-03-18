-- Add recurring flag to transactions
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS recurring BOOLEAN DEFAULT FALSE;

-- Mark all transactions currently in "Subscriptions" category as recurring
UPDATE transactions SET recurring = TRUE
WHERE category_id = (SELECT id FROM categories WHERE name = 'Subscriptions' AND deleted_at IS NULL);

-- Also mark known recurring payee patterns
UPDATE transactions SET recurring = TRUE
WHERE recurring = FALSE AND (
    lower(COALESCE(payee, description)) LIKE '%tmobile%auto pay%'
    OR lower(COALESCE(payee, description)) LIKE '%comcast%xfinity%'
    OR lower(COALESCE(payee, description)) LIKE '%astound%'
    OR lower(COALESCE(payee, description)) LIKE '%allstate%'
    OR lower(COALESCE(payee, description)) LIKE '%new york life%'
    OR lower(COALESCE(payee, description)) LIKE '%northwestern mu%'
    OR lower(COALESCE(payee, description)) LIKE '%nicor gas%'
    OR lower(COALESCE(payee, description)) LIKE '%comed%'
    OR lower(COALESCE(payee, description)) LIKE '%village of orlan%'
    OR lower(COALESCE(payee, description)) LIKE '%ford motor cr%'
    OR lower(COALESCE(payee, description)) LIKE '%toyota ach%'
    OR lower(COALESCE(payee, description)) LIKE '%vgi 529%'
    OR lower(COALESCE(payee, description)) LIKE '%bb tuition%'
    OR lower(COALESCE(payee, description)) LIKE '%cross keys school%'
);
