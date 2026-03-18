"""Spending analytics router — by-category, by-payee, over-time, deltas, flow, subscriptions."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter

from db import db_conn, db_put

router = APIRouter(prefix="/api/spending", tags=["spending"])


@router.get("/by-category")
def spending_by_category(start_date: Optional[date] = None, end_date: Optional[date] = None,
                         account_id: Optional[str] = None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        f = ["t.amount < 0", "t.pending = FALSE", "t.is_transfer = FALSE"]; p = []
        if start_date: f.append("t.posted >= %s"); p.append(start_date)
        if end_date: f.append("t.posted <= %s"); p.append(end_date)
        if account_id: f.append("t.account_id = %s"); p.append(account_id)
        cur.execute(
            f"SELECT COALESCE(c.name, 'Uncategorized'), c.color, c.group_name, SUM(ABS(t.amount)), COUNT(*) "
            f"FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            f"WHERE {' AND '.join(f)} GROUP BY c.name, c.color, c.group_name ORDER BY 4 DESC", p)
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"category": r[0], "color": r[1] or "#475569", "group": r[2],
             "total": float(r[3]), "count": r[4]} for r in rows]


@router.get("/by-payee")
def spending_by_payee(start_date: Optional[date] = None, end_date: Optional[date] = None,
                      limit: int = 25, account_id: Optional[str] = None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        f = ["amount < 0", "pending = FALSE", "is_transfer = FALSE"]; p = []
        if start_date: f.append("posted >= %s"); p.append(start_date)
        if end_date: f.append("posted <= %s"); p.append(end_date)
        if account_id: f.append("account_id = %s"); p.append(account_id)
        cur.execute(
            f"SELECT COALESCE(payee, description, 'Unknown'), SUM(ABS(amount)), COUNT(*) "
            f"FROM transactions WHERE {' AND '.join(f)} GROUP BY 1 ORDER BY 2 DESC LIMIT %s", p + [limit])
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"payee": r[0], "total": float(r[1]), "count": r[2]} for r in rows]


@router.get("/over-time")
def spending_over_time(months: int = 6, account_id: Optional[str] = None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        f = ["pending = FALSE", "is_transfer = FALSE"]; p = []
        if account_id: f.append("account_id = %s"); p.append(account_id)
        cur.execute(
            f"SELECT TO_CHAR(posted, 'YYYY-MM'), "
            f"SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), "
            f"SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) "
            f"FROM transactions WHERE {' AND '.join(f)} GROUP BY 1 ORDER BY 1 DESC LIMIT %s", p + [months])
        rows = cur.fetchall()
    finally:
        db_put(conn)
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
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(c.name, 'Uncategorized'), c.color, SUM(ABS(t.amount)) "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND t.posted >= %s AND t.posted <= %s GROUP BY c.name, c.color",
            (start_date, end_date))
        current = {r[0]: {"color": r[1] or "#475569", "total": float(r[2])} for r in cur.fetchall()}
        cur.execute(
            "SELECT COALESCE(c.name, 'Uncategorized'), SUM(ABS(t.amount)) "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND t.posted >= %s AND t.posted <= %s GROUP BY c.name",
            (ps, pe))
        prior = {r[0]: float(r[1]) for r in cur.fetchall()}
    finally:
        db_put(conn)
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
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(c.name, 'Other Income'), c.color, SUM(t.amount) "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount > 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND t.posted >= %s AND t.posted <= %s GROUP BY c.name, c.color ORDER BY 3 DESC",
            (start_date, end_date))
        income = [{"name": r[0], "color": r[1] or "#4ade80", "amount": float(r[2])} for r in cur.fetchall()]
        cur.execute(
            "SELECT COALESCE(c.name, 'Uncategorized'), c.color, SUM(ABS(t.amount)) "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND t.posted >= %s AND t.posted <= %s GROUP BY c.name, c.color ORDER BY 3 DESC",
            (start_date, end_date))
        spending = [{"name": r[0], "color": r[1] or "#475569", "amount": float(r[2])} for r in cur.fetchall()]
    finally:
        db_put(conn)
    total_in = sum(i["amount"] for i in income)
    total_out = sum(s["amount"] for s in spending)
    return {"income": income, "spending": spending, "total_income": total_in, "total_spending": total_out,
            "net": total_in - total_out,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()}}


# ── Subscriptions (mounted under /api/subscriptions, not /api/spending) ──
sub_router = APIRouter(prefix="/api/subscriptions", tags=["spending"])


@sub_router.get("/detect")
def detect_subscriptions(min_months: int = 3, amount_tolerance_pct: float = 15):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(payee, description), posted, amount "
            "FROM transactions WHERE amount < 0 AND pending = FALSE AND is_transfer = FALSE "
            "AND COALESCE(payee, description) IS NOT NULL ORDER BY 1, posted")
        rows = cur.fetchall()
    finally:
        db_put(conn)
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
