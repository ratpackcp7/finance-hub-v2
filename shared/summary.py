"""
Shared helpers for monthly spending summaries and balance snapshots.

C.7: Extracted from digest.py, worker.py, and accounts.py to eliminate
duplicated query logic. All callers pass a cursor; transaction management
stays with the caller.
"""
import calendar
from datetime import date, timedelta
from typing import Optional


def get_month_range(month_str: Optional[str] = None):
    """Parse YYYY-MM or default to last complete month.

    Returns (start_date, end_date, label_str).
    """
    if month_str:
        yr, mo = int(month_str[:4]), int(month_str[5:7])
    else:
        today = date.today()
        first_of_this = date(today.year, today.month, 1)
        last_month_end = first_of_this - timedelta(days=1)
        yr, mo = last_month_end.year, last_month_end.month
    last_day = calendar.monthrange(yr, mo)[1]
    return date(yr, mo, 1), date(yr, mo, last_day), f"{yr}-{mo:02d}"


def monthly_spending_summary(cur, start: date, end: date) -> dict:
    """Compute income, spending, top categories for a date range.

    Returns dict with keys: income, spending, net, savings_rate, top_categories.
    Used by both digest.py (API) and worker.py (Telegram cron).
    """
    # Income
    cur.execute(
        "SELECT COALESCE(SUM(t.amount), 0) FROM transactions t "
        "LEFT JOIN categories c ON t.category_id = c.id "
        "WHERE t.amount > 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
        "AND COALESCE(c.is_income, FALSE) = TRUE "
        "AND t.posted >= %s AND t.posted <= %s", (start, end))
    income = float(cur.fetchone()[0])

    # Spending (via spending_items view)
    cur.execute(
        "SELECT COALESCE(SUM(ABS(t.amount)), 0) FROM spending_items t "
        "LEFT JOIN categories c ON t.category_id = c.id "
        "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
        "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
        "AND t.posted >= %s AND t.posted <= %s", (start, end))
    spending = float(cur.fetchone()[0])

    net = income - spending
    savings_rate = ((income - spending) / income * 100) if income > 0 else 0

    # Top 5 spending categories
    cur.execute(
        "SELECT COALESCE(c.name, 'Uncategorized'), SUM(ABS(t.amount)) "
        "FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
        "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
        "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
        "AND t.posted >= %s AND t.posted <= %s "
        "GROUP BY c.name ORDER BY 2 DESC LIMIT 5", (start, end))
    top_categories = [{"category": r[0], "amount": float(r[1])} for r in cur.fetchall()]

    return {
        "income": round(income, 2),
        "spending": round(spending, 2),
        "net": round(net, 2),
        "savings_rate": round(savings_rate, 1),
        "top_categories": top_categories,
    }


def take_balance_snapshot(cur, snapshot_date: Optional[date] = None) -> int:
    """Record current account balances. Idempotent per date.

    Returns row count (number of accounts snapshotted).
    Used by both accounts.py (API endpoint) and worker.py (cron).
    """
    if snapshot_date is None:
        snapshot_date = date.today()
    cur.execute(
        """INSERT INTO balance_snapshots (snapshot_date, account_id, account_name, account_type, balance)
           SELECT %s, id, name, COALESCE(account_type, 'checking'), balance
           FROM accounts WHERE hidden = FALSE AND balance IS NOT NULL
           ON CONFLICT (snapshot_date, account_id) DO UPDATE SET
             balance = EXCLUDED.balance,
             account_name = EXCLUDED.account_name,
             account_type = EXCLUDED.account_type""",
        (snapshot_date,))
    return cur.rowcount


def net_worth_at(cur, as_of: date) -> Optional[float]:
    """Get net worth from the latest snapshot on or before as_of."""
    cur.execute(
        "SELECT SUM(balance) FROM balance_snapshots "
        "WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM balance_snapshots WHERE snapshot_date <= %s)",
        (as_of,))
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None
