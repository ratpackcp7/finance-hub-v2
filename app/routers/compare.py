"""Period comparison router — compare spending across two arbitrary date ranges."""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter

from db import db_read, db_transaction

router = APIRouter(prefix="/api/compare", tags=["compare"])


@router.get("/periods")
def compare_periods(
    start_a: date, end_a: date,
    start_b: date, end_b: date,
    account_id: Optional[str] = None
):
    """Compare spending, income, and category breakdown between two periods."""
    with db_read() as cur:
        acct_filter = "AND t.account_id = %s" if account_id else ""
        acct_params = [account_id] if account_id else []

        results = {}
        for label, start, end in [("a", start_a, end_a), ("b", start_b, end_b)]:
            # Income
            cur.execute(
                f"SELECT COALESCE(SUM(t.amount), 0) FROM transactions t "
                f"LEFT JOIN categories c ON t.category_id = c.id "
                f"WHERE t.amount > 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
                f"AND COALESCE(c.is_income, FALSE) = TRUE "
                f"AND t.posted >= %s AND t.posted <= %s {acct_filter}",
                [start, end] + acct_params)
            income = float(cur.fetchone()[0])

            # Spending
            cur.execute(
                f"SELECT COALESCE(SUM(ABS(t.amount)), 0) FROM spending_items t "
                f"LEFT JOIN categories c ON t.category_id = c.id "
                f"WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
                f"AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
                f"AND t.posted >= %s AND t.posted <= %s {acct_filter}",
                [start, end] + acct_params)
            spending = float(cur.fetchone()[0])

            # By category
            cur.execute(
                f"SELECT COALESCE(c.name, 'Uncategorized'), c.color, SUM(ABS(t.amount)) "
                f"FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
                f"WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
                f"AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
                f"AND t.posted >= %s AND t.posted <= %s {acct_filter} "
                f"GROUP BY c.name, c.color ORDER BY 3 DESC",
                [start, end] + acct_params)
            categories = [{"category": r[0], "color": r[1] or "#475569",
                          "amount": float(r[2])} for r in cur.fetchall()]

            # Top payees
            cur.execute(
                f"SELECT COALESCE(t.payee, t.description, 'Unknown'), SUM(ABS(t.amount)) "
                f"FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
                f"WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
                f"AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
                f"AND t.posted >= %s AND t.posted <= %s {acct_filter} "
                f"GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
                [start, end] + acct_params)
            payees = [{"payee": r[0], "amount": float(r[1])} for r in cur.fetchall()]

            # Transaction count
            cur.execute(
                f"SELECT COUNT(*) FROM transactions t "
                f"WHERE t.pending = FALSE AND t.is_transfer = FALSE "
                f"AND t.posted >= %s AND t.posted <= %s {acct_filter}",
                [start, end] + acct_params)
            txn_count = cur.fetchone()[0]

            results[label] = {
                "period": {"start": start.isoformat(), "end": end.isoformat()},
                "income": round(income, 2),
                "spending": round(spending, 2),
                "net": round(income - spending, 2),
                "txn_count": txn_count,
                "categories": categories,
                "top_payees": payees,
            }

    # Compute deltas
    deltas = {
        "income": round(results["a"]["income"] - results["b"]["income"], 2),
        "spending": round(results["a"]["spending"] - results["b"]["spending"], 2),
        "net": round(results["a"]["net"] - results["b"]["net"], 2),
    }

    # Category comparison
    cats_a = {c["category"]: c["amount"] for c in results["a"]["categories"]}
    cats_b = {c["category"]: c["amount"] for c in results["b"]["categories"]}
    all_cats = sorted(set(list(cats_a.keys()) + list(cats_b.keys())))
    cat_comparison = []
    for cat in all_cats:
        a_val = cats_a.get(cat, 0)
        b_val = cats_b.get(cat, 0)
        delta = a_val - b_val
        pct = ((delta / b_val) * 100) if b_val > 0 else (100 if a_val > 0 else 0)
        color = next((c["color"] for c in results["a"]["categories"] + results["b"]["categories"]
                      if c["category"] == cat), "#475569")
        cat_comparison.append({
            "category": cat, "color": color,
            "period_a": round(a_val, 2), "period_b": round(b_val, 2),
            "delta": round(delta, 2), "pct_change": round(pct, 1),
        })
    cat_comparison.sort(key=lambda x: abs(x["delta"]), reverse=True)

    return {
        "period_a": results["a"],
        "period_b": results["b"],
        "deltas": deltas,
        "category_comparison": cat_comparison,
    }
