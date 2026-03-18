"""Shared SQL filter definitions — single source of truth for income/spending/category rules.

Every endpoint that needs to distinguish income from spending, or exclude
non-real-spending categories, MUST use these constants and helpers.

Rules:
  REAL TRANSACTION = pending = FALSE
  INCOME  = amount > 0, not a transfer, category has is_income = TRUE
  SPENDING = amount < 0, not a transfer, category not in EXCLUDED_SPENDING_CATEGORIES
  EXCLUDED_SPENDING_CATEGORIES = categories that represent money movement, not real spending
"""

# ─── Category exclusion list ───
# These categories represent internal money movement, not real income or spending.
# They should be excluded from spending totals, flow charts, budgets, trends, etc.
EXCLUDED_SPENDING_CATEGORIES = ("Credit Card Pay", "Transfer")

# ─── SQL fragments (use with table aliases: t=transactions, c=categories) ───

# Base: real (non-pending) transactions
SQL_REAL_TXN = "t.pending = FALSE"

# Exclude transfers
SQL_NOT_TRANSFER = "t.is_transfer = FALSE"

# Income: positive amount in an income-flagged category, not a transfer
SQL_IS_INCOME = (
    "t.amount > 0 AND t.is_transfer = FALSE AND COALESCE(c.is_income, FALSE) = TRUE"
)

# Spending: negative amount, not a transfer, not in excluded categories
SQL_IS_SPENDING = (
    "t.amount < 0 AND t.is_transfer = FALSE "
    "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer')"
)

# For CASE statements in aggregate queries (over-time, etc.)
SQL_CASE_INCOME = "CASE WHEN {} THEN t.amount ELSE 0 END".format(SQL_IS_INCOME)
SQL_CASE_SPENDING = "CASE WHEN {} THEN ABS(t.amount) ELSE 0 END".format(SQL_IS_SPENDING)

# Common WHERE clause combos
SQL_WHERE_SPENDING = f"{SQL_REAL_TXN} AND {SQL_IS_SPENDING}"
SQL_WHERE_INCOME = f"{SQL_REAL_TXN} AND {SQL_IS_INCOME}"


def spending_filters():
    """Return base filters list for spending queries (amount < 0, not transfer, not CC Pay)."""
    return [
        "t.amount < 0",
        "t.pending = FALSE",
        "t.is_transfer = FALSE",
        "COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer')",
    ]


def income_filters():
    """Return base filters list for income queries."""
    return [
        "t.amount > 0",
        "t.pending = FALSE",
        "t.is_transfer = FALSE",
        "COALESCE(c.is_income, FALSE) = TRUE",
    ]
