"""Spending analytics router — by-category, by-payee, over-time, deltas, flow, subscriptions."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter

from db import db_read, db_transaction
from filters import spending_filters, SQL_CASE_INCOME, SQL_CASE_SPENDING

router = APIRouter(prefix="/api/spending", tags=["spending"])


@router.get("/by-category")
def spending_by_category(start_date: Optional[date] = None, end_date: Optional[date] = None,
                         account_id: Optional[str] = None):
    with db_read() as cur:
        f = spending_filters(); p = []
        if start_date: f.append("t.posted >= %s"); p.append(start_date)
        if end_date: f.append("t.posted <= %s"); p.append(end_date)
        if account_id: f.append("t.account_id = %s"); p.append(account_id)
        cur.execute(
            f"SELECT COALESCE(c.name, 'Uncategorized'), c.color, c.group_name, SUM(ABS(t.amount)), COUNT(*) "
            f"FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
            f"WHERE {' AND '.join(f)} GROUP BY c.name, c.color, c.group_name ORDER BY 4 DESC", p)
        rows = cur.fetchall()
    return [{"category": r[0], "color": r[1] or "#475569", "group": r[2],
             "total": float(r[3]), "count": r[4]} for r in rows]


@router.get("/by-payee")
def spending_by_payee(start_date: Optional[date] = None, end_date: Optional[date] = None,
                      limit: int = 25, account_id: Optional[str] = None):
    with db_read() as cur:
        f = spending_filters(); p = []
        if start_date: f.append("posted >= %s"); p.append(start_date)
        if end_date: f.append("posted <= %s"); p.append(end_date)
        if account_id: f.append("account_id = %s"); p.append(account_id)
        cur.execute(
            f"SELECT COALESCE(t.payee, t.description, 'Unknown'), SUM(ABS(t.amount)), COUNT(*) "
            f"FROM transactions t LEFT JOIN categories c ON t.category_id = c.id WHERE {' AND '.join(f)} GROUP BY 1 ORDER BY 2 DESC LIMIT %s", p + [limit])
        rows = cur.fetchall()
    return [{"payee": r[0], "total": float(r[1]), "count": r[2]} for r in rows]


@router.get("/over-time")
def spending_over_time(months: int = 6, account_id: Optional[str] = None):
    with db_read() as cur:
        f = ["t.pending = FALSE", "t.is_transfer = FALSE"]; p = []
        if account_id: f.append("t.account_id = %s"); p.append(account_id)
        # Income: only count positive txns in income categories (Paycheck, Other Income, Investment)
        # Spending: only count negative txns NOT in income categories and NOT CC Pay
        cur.execute(
            f"SELECT TO_CHAR(t.posted, 'YYYY-MM'), "
            f"SUM({SQL_CASE_SPENDING}), "
            f"SUM({SQL_CASE_INCOME}) "
            f"FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            f"WHERE {' AND '.join(f)} GROUP BY 1 ORDER BY 1 DESC LIMIT %s", p + [months])
        rows = cur.fetchall()
    return [{"month": r[0], "spending": float(r[1]), "income": float(r[2])} for r in rows]


@router.get("/deltas")
def spending_deltas(start_date: Optional[date] = None, end_date: Optional[date] = None):
    now = datetime.now()
    if not start_date:
        start_date = date(now.year, now.month, 1)
    if not end_date:
        end_date = (date(now.year, 12, 31) if now.month == 12
                    else date(now.year, now.month + 1, 1) - timedelta(days=1))
    pd = (end_date - start_date).days + 1
    pe = start_date - timedelta(days=1)
    ps = pe - timedelta(days=pd - 1)
    with db_read() as cur:
        cur.execute(
            "SELECT COALESCE(c.name, 'Uncategorized'), c.color, SUM(ABS(t.amount)) "
            "FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
            "AND t.posted >= %s AND t.posted <= %s GROUP BY c.name, c.color",
            (start_date, end_date))
        current = {r[0]: {"color": r[1] or "#475569", "total": float(r[2])} for r in cur.fetchall()}
        cur.execute(
            "SELECT COALESCE(c.name, 'Uncategorized'), SUM(ABS(t.amount)) "
            "FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
            "AND t.posted >= %s AND t.posted <= %s GROUP BY c.name",
            (ps, pe))
        prior = {r[0]: float(r[1]) for r in cur.fetchall()}
    results = []
    for cat in sorted(set(list(current.keys()) + list(prior.keys()))):
        ct = current.get(cat, {}).get("total", 0)
        pt = prior.get(cat, 0)
        d = ct - pt
        pct = ((d / pt) * 100) if pt > 0 else (100 if ct > 0 else 0)
        results.append({"category": cat, "color": current.get(cat, {}).get("color", "#475569"),
                        "current": ct, "previous": pt, "delta": round(d, 2), "pct_change": round(pct, 1)})
    results.sort(key=lambda x: abs(x["delta"]), reverse=True)
    tc = sum(r["current"] for r in results)
    tp = sum(r["previous"] for r in results)
    return {"deltas": results,
            "totals": {"current": round(tc, 2), "previous": round(tp, 2), "delta": round(tc - tp, 2)},
            "period": {"current": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                       "previous": {"start": ps.isoformat(), "end": pe.isoformat()}}}


@router.get("/flow")
def spending_flow(start_date: Optional[date] = None, end_date: Optional[date] = None):
    now = datetime.now()
    if not start_date:
        start_date = date(now.year, now.month, 1)
    if not end_date:
        end_date = (date(now.year, 12, 31) if now.month == 12
                    else date(now.year, now.month + 1, 1) - timedelta(days=1))
    with db_read() as cur:
        cur.execute(
            "SELECT COALESCE(c.name, 'Other Income'), c.color, SUM(t.amount) "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount > 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.is_income, FALSE) = TRUE "
            "AND t.posted >= %s AND t.posted <= %s GROUP BY c.name, c.color ORDER BY 3 DESC",
            (start_date, end_date))
        income = [{"name": r[0], "color": r[1] or "#4ade80", "amount": float(r[2])} for r in cur.fetchall()]
        cur.execute(
            "SELECT COALESCE(c.name, 'Uncategorized'), c.color, SUM(ABS(t.amount)) "
            "FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
            "AND t.posted >= %s AND t.posted <= %s GROUP BY c.name, c.color ORDER BY 3 DESC",
            (start_date, end_date))
        spending = [{"name": r[0], "color": r[1] or "#475569", "amount": float(r[2])} for r in cur.fetchall()]
    total_in = sum(i["amount"] for i in income)
    total_out = sum(s["amount"] for s in spending)
    return {"income": income, "spending": spending, "total_income": total_in, "total_spending": total_out,
            "net": total_in - total_out,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()}}


# ── Subscriptions (mounted under /api/subscriptions, not /api/spending) ──
sub_router = APIRouter(prefix="/api/subscriptions", tags=["spending"])


@sub_router.get("/detect")
def detect_subscriptions(min_months: int = 3, amount_tolerance_pct: float = 15):
    with db_read() as cur:
        cur.execute(
            "SELECT COALESCE(t.payee, t.description), t.posted, t.amount "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
            "AND COALESCE(t.payee, t.description) IS NOT NULL ORDER BY 1, t.posted")
        rows = cur.fetchall()
    by_payee = defaultdict(list)
    for label, posted, amount in rows:
        by_payee[label].append({"posted": posted, "amount": float(amount)})
    subs = []
    for payee, txns in by_payee.items():
        if len(txns) < min_months:
            continue
        amounts = [abs(t["amount"]) for t in txns]
        med = sorted(amounts)[len(amounts) // 2]
        if med < 1:
            continue
        tol = med * (amount_tolerance_pct / 100)
        con = sorted([t for t in txns if abs(abs(t["amount"]) - med) <= tol], key=lambda t: t["posted"])
        if len(con) < max(min_months, 2):
            continue
        gaps = [(con[i]["posted"] - con[i - 1]["posted"]).days for i in range(1, len(con))]
        avg = sum(gaps) / len(gaps) if gaps else 0
        if avg < 20 or avg > 45:
            continue
        last = con[-1]
        subs.append({"payee": payee, "typical_amount": round(med, 2), "annual_cost": round(med * 12, 2),
                     "frequency_days": round(avg, 0), "charge_count": len(con),
                     "last_date": last["posted"].isoformat(), "last_amount": round(abs(last["amount"]), 2)})
    subs.sort(key=lambda s: s["annual_cost"], reverse=True)
    ta = sum(s["annual_cost"] for s in subs)
    return {"subscriptions": subs, "totals": {"annual": round(ta, 2), "monthly": round(ta / 12, 2)}}


@router.get("/budget-progress")
def budget_progress(month: Optional[str] = None):
    """Budget vs actual spending for a given month."""
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    parts = month.split("-")
    yr, mo = int(parts[0]), int(parts[1])
    start_date = date(yr, mo, 1)
    end_date = date(yr + (1 if mo == 12 else 0), (1 if mo == 12 else mo + 1), 1)
    with db_read() as cur:
        cur.execute(
            "SELECT b.id, b.category_id, c.name, c.color, b.monthly_amount "
            "FROM budgets b JOIN categories c ON b.category_id = c.id "
            "ORDER BY b.monthly_amount DESC")
        budgets = cur.fetchall()
        cur.execute(
            "SELECT t.category_id, SUM(ABS(t.amount)) "
            "FROM spending_items t "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND t.posted >= %s AND t.posted < %s "
            "GROUP BY t.category_id", (start_date, end_date))
        actuals = {r[0]: float(r[1]) for r in cur.fetchall()}
    import calendar
    days_in_month = calendar.monthrange(yr, mo)[1]
    today = date.today()
    day_of_month = today.day if (today.year == yr and today.month == mo) else days_in_month
    pct_through = day_of_month / days_in_month
    results, total_budget, total_actual, over_count = [], 0, 0, 0
    for b in budgets:
        cat_id, cat_name, color, budget_amt = b[1], b[2], b[3], float(b[4])
        actual = actuals.get(cat_id, 0)
        pct_used = (actual / budget_amt * 100) if budget_amt > 0 else 0
        total_budget += budget_amt; total_actual += actual
        if actual > budget_amt: over_count += 1
        results.append({"category": cat_name, "category_id": cat_id, "color": color or "#475569",
            "budget": budget_amt, "actual": actual, "remaining": budget_amt - actual,
            "pct_used": round(pct_used, 1), "over": actual > budget_amt})
    return {"month": month, "day_of_month": day_of_month, "days_in_month": days_in_month,
        "pct_through": round(pct_through * 100, 1), "categories": results,
        "summary": {"total_budget": total_budget, "total_actual": total_actual,
            "total_remaining": total_budget - total_actual,
            "over_count": over_count, "on_track": len(results) - over_count}}


@router.get("/budget-vs-actual")
def budget_vs_actual(month: Optional[str] = None):
    """Budget vs actual spending for a given month (YYYY-MM). Defaults to current month."""
    if month:
        yr, mo = int(month[:4]), int(month[5:7])
    else:
        today = date.today()
        yr, mo = today.year, today.month

    import calendar as cal
    last_day = cal.monthrange(yr, mo)[1]
    start = date(yr, mo, 1)
    end = date(yr, mo, last_day)

    with db_read() as cur:
        # Get all budgets
        cur.execute(
            "SELECT b.id, b.category_id, c.name, c.color, b.monthly_amount "
            "FROM budgets b JOIN categories c ON b.category_id = c.id "
            "ORDER BY b.monthly_amount DESC")
        budgets = cur.fetchall()

        # Get actual spending per category for the month
        cur.execute(
            "SELECT t.category_id, SUM(ABS(t.amount)) "
            "FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
            "AND t.posted >= %s AND t.posted <= %s "
            "GROUP BY t.category_id", (start, end))
        actuals = dict(cur.fetchall())

    results = []
    total_budget = 0
    total_actual = 0
    for b in budgets:
        budget_id, cat_id, cat_name, color, budget_amt = b
        actual = float(actuals.get(cat_id, 0))
        pct = (actual / float(budget_amt) * 100) if budget_amt else 0
        results.append({
            "category": cat_name,
            "category_id": cat_id,
            "color": color or "#475569",
            "budget": float(budget_amt),
            "actual": actual,
            "remaining": float(budget_amt) - actual,
            "pct": round(pct, 1),
        })
        total_budget += float(budget_amt)
        total_actual += actual

    # Also compute how many days into the month / expected pacing
    today = date.today()
    if yr == today.year and mo == today.month:
        days_in = today.day
        days_total = last_day
        pacing_pct = round(days_in / days_total * 100, 1)
    else:
        days_in = last_day
        days_total = last_day
        pacing_pct = 100.0

    return {
        "month": f"{yr}-{mo:02d}",
        "items": results,
        "total_budget": total_budget,
        "total_actual": total_actual,
        "pacing_pct": pacing_pct,
        "days_in": days_in,
        "days_total": days_total,
    }


@router.get("/trends")
def spending_trends(months: int = 3, top: int = 6):
    """Monthly spending for top N categories over last N months."""
    from collections import defaultdict
    with db_read() as cur:
        cutoff = date.today().replace(day=1) - timedelta(days=months * 31)
        cur.execute(
            "SELECT DATE_TRUNC('month', t.posted)::date AS m, "
            "COALESCE(c.name, 'Uncategorized') AS cat, c.color, "
            "SUM(ABS(t.amount)) "
            "FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND t.posted >= %s AND c.name NOT IN ('Credit Card Pay', 'Transfer') "
            "GROUP BY m, cat, c.color ORDER BY m ASC, 4 DESC", (cutoff,))
        rows = cur.fetchall()

    # Find top categories by total spend
    cat_totals = defaultdict(float)
    cat_colors = {}
    for r in rows:
        cat_totals[r[1]] += float(r[3])
        cat_colors[r[1]] = r[2] or '#475569'

    top_cats = sorted(cat_totals, key=cat_totals.get, reverse=True)[:top]

    # Build monthly series per category
    all_months = sorted(set(r[0].strftime('%Y-%m') for r in rows))
    series = {}
    for r in rows:
        cat = r[1]
        if cat in top_cats:
            m = r[0].strftime('%Y-%m')
            if cat not in series:
                series[cat] = {"color": cat_colors[cat], "data": {}}
            series[cat]["data"][m] = float(r[3])

    return {
        "months": all_months,
        "categories": [
            {
                "name": cat,
                "color": cat_colors[cat],
                "values": [series.get(cat, {}).get("data", {}).get(m, 0) for m in all_months]
            }
            for cat in top_cats
        ]
    }
