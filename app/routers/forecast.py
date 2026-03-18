"""Spending forecast router — cashflow projection, category forecast, what-if scenarios."""
import math
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter

from db import db_conn, db_put

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


def _get_monthly_averages(cur, months=3):
    """Get average income/spending per month over last N complete months."""
    today = date.today()
    # Exclude current (incomplete) month
    end = date(today.year, today.month, 1) - timedelta(days=1)
    start = date(end.year, end.month - months + 1, 1) if end.month > months else date(end.year - 1, end.month + 12 - months + 1, 1)

    # Income
    cur.execute(
        "SELECT COALESCE(SUM(t.amount), 0) / %s FROM transactions t "
        "LEFT JOIN categories c ON t.category_id = c.id "
        "WHERE t.amount > 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
        "AND COALESCE(c.is_income, FALSE) = TRUE "
        "AND t.posted >= %s AND t.posted <= %s",
        (months, start, end))
    avg_income = float(cur.fetchone()[0])

    # Spending
    cur.execute(
        "SELECT COALESCE(SUM(ABS(t.amount)), 0) / %s FROM spending_items t "
        "LEFT JOIN categories c ON t.category_id = c.id "
        "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
        "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
        "AND t.posted >= %s AND t.posted <= %s",
        (months, start, end))
    avg_spending = float(cur.fetchone()[0])

    return avg_income, avg_spending, start, end


@router.get("/cashflow")
def cashflow_forecast(months_ahead: int = 6):
    """Project monthly cashflow for the next N months."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        avg_income, avg_spending, hist_start, hist_end = _get_monthly_averages(cur, 3)
        savings_rate = ((avg_income - avg_spending) / avg_income * 100) if avg_income > 0 else 0

        # Get actual monthly history for chart baseline
        cur.execute(
            "SELECT TO_CHAR(t.posted, 'YYYY-MM'), "
            "SUM(CASE WHEN t.amount > 0 AND t.is_transfer = FALSE AND COALESCE(c.is_income, FALSE) = TRUE THEN t.amount ELSE 0 END), "
            "SUM(CASE WHEN t.amount < 0 AND t.is_transfer = FALSE AND COALESCE(c.name,'') NOT IN ('Credit Card Pay','Transfer') THEN ABS(t.amount) ELSE 0 END) "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.pending = FALSE AND t.posted >= %s "
            "GROUP BY 1 ORDER BY 1", (hist_start,))
        actuals = [{"month": r[0], "income": float(r[1]), "spending": float(r[2]),
                    "net": float(r[1]) - float(r[2]), "type": "actual"} for r in cur.fetchall()]

        # Current net worth for cumulative projection
        cur.execute("SELECT SUM(balance) FROM accounts WHERE hidden = FALSE")
        current_nw = float(cur.fetchone()[0] or 0)

        # Project future months
        today = date.today()
        projections = []
        cumulative_savings = 0
        for i in range(1, months_ahead + 1):
            m = today.month + i
            y = today.year + (m - 1) // 12
            m = ((m - 1) % 12) + 1
            label = f"{y}-{m:02d}"
            net = avg_income - avg_spending
            cumulative_savings += net
            projections.append({
                "month": label,
                "income": round(avg_income, 2),
                "spending": round(avg_spending, 2),
                "net": round(net, 2),
                "cumulative_savings": round(cumulative_savings, 2),
                "projected_nw": round(current_nw + cumulative_savings, 2),
                "type": "projected",
            })
    finally:
        db_put(conn)

    return {
        "averages": {
            "income": round(avg_income, 2),
            "spending": round(avg_spending, 2),
            "net": round(avg_income - avg_spending, 2),
            "savings_rate": round(savings_rate, 1),
        },
        "current_net_worth": round(current_nw, 2),
        "actuals": actuals,
        "projections": projections,
    }


@router.get("/category")
def category_forecast():
    """Per-category spending projection based on recent averages."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        today = date.today()
        end = date(today.year, today.month, 1) - timedelta(days=1)
        start = date(end.year if end.month >= 3 else end.year - 1,
                     end.month - 2 if end.month >= 3 else end.month + 10, 1)

        cur.execute(
            """SELECT COALESCE(c.name, 'Uncategorized'), c.color,
                      SUM(ABS(t.amount)) / 3.0,
                      COUNT(*) / 3.0
               FROM spending_items t
               LEFT JOIN categories c ON t.category_id = c.id
               WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE
               AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer')
               AND t.posted >= %s AND t.posted <= %s
               GROUP BY c.name, c.color
               ORDER BY 3 DESC""", (start, end))
        avg_rows = cur.fetchall()

        # Current month spending so far
        month_start = date(today.year, today.month, 1)
        cur.execute(
            """SELECT COALESCE(c.name, 'Uncategorized'), SUM(ABS(t.amount))
               FROM spending_items t
               LEFT JOIN categories c ON t.category_id = c.id
               WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE
               AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer')
               AND t.posted >= %s
               GROUP BY c.name""", (month_start,))
        current = {r[0]: float(r[1]) for r in cur.fetchall()}

        # Budget targets
        cur.execute(
            "SELECT c.name, b.monthly_amount FROM budgets b "
            "JOIN categories c ON b.category_id = c.id WHERE b.deleted_at IS NULL")
        budgets = {r[0]: float(r[1]) for r in cur.fetchall()}
    finally:
        db_put(conn)

    import calendar
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    day_of_month = today.day
    pace_factor = days_in_month / max(day_of_month, 1)

    categories = []
    for name, color, avg_monthly, avg_count in avg_rows:
        cur_amount = current.get(name, 0)
        projected = cur_amount * pace_factor  # pace-based projection
        budget = budgets.get(name)
        trend = "over" if budget and projected > budget else "on_track" if budget else "no_budget"

        categories.append({
            "category": name,
            "color": color or "#475569",
            "avg_monthly": round(float(avg_monthly), 2),
            "current_month": round(cur_amount, 2),
            "projected_month": round(projected, 2),
            "budget": budget,
            "trend": trend,
            "avg_txns_per_month": round(float(avg_count), 1),
        })

    return {"categories": categories, "month": today.strftime("%Y-%m"),
            "days_elapsed": day_of_month, "days_total": days_in_month}


@router.get("/what-if")
def what_if(category: Optional[str] = None, monthly_change: float = 0,
            extra_savings: float = 0, months: int = 12):
    """What-if scenario: reduce category spending or add extra savings."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        avg_income, avg_spending, _, _ = _get_monthly_averages(cur, 3)

        # Current net worth
        cur.execute("SELECT SUM(balance) FROM accounts WHERE hidden = FALSE")
        current_nw = float(cur.fetchone()[0] or 0)
    finally:
        db_put(conn)

    # Baseline scenario
    baseline_net = avg_income - avg_spending
    baseline_savings = [round(baseline_net * i, 2) for i in range(1, months + 1)]

    # Modified scenario
    adjusted_spending = avg_spending + monthly_change  # negative = reduction
    adjusted_net = avg_income - adjusted_spending + extra_savings
    adjusted_savings = [round(adjusted_net * i, 2) for i in range(1, months + 1)]

    diff_monthly = adjusted_net - baseline_net
    diff_total = diff_monthly * months

    return {
        "baseline": {
            "monthly_net": round(baseline_net, 2),
            "annual_savings": round(baseline_net * 12, 2),
            "nw_in_months": round(current_nw + baseline_net * months, 2),
        },
        "adjusted": {
            "monthly_net": round(adjusted_net, 2),
            "annual_savings": round(adjusted_net * 12, 2),
            "nw_in_months": round(current_nw + adjusted_net * months, 2),
            "spending_change": monthly_change,
            "extra_savings": extra_savings,
        },
        "impact": {
            "monthly_improvement": round(diff_monthly, 2),
            "total_improvement": round(diff_total, 2),
            "months": months,
        },
        "series_baseline": baseline_savings,
        "series_adjusted": adjusted_savings,
    }
