"""Budgets router — CRUD + status, soft-delete aware."""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_read, db_transaction, require_valid_category

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


@router.get("")
def get_budgets():
    with db_read() as cur:
        cur.execute(
            "SELECT b.id, b.category_id, c.name, c.color, b.monthly_amount "
            "FROM budgets b JOIN categories c ON b.category_id = c.id "
            "WHERE b.deleted_at IS NULL AND c.deleted_at IS NULL ORDER BY c.sort_order, c.name")
        rows = cur.fetchall()
    return [{"id": r[0], "category_id": r[1], "category": r[2], "color": r[3],
             "monthly_amount": float(r[4])} for r in rows]


class BudgetCreate(BaseModel):
    category_id: int
    monthly_amount: float


@router.post("", status_code=201)
def create_or_update_budget(body: BudgetCreate):
    if body.monthly_amount <= 0:
        raise HTTPException(status_code=400, detail="monthly_amount must be positive")
    with db_transaction() as cur:
        require_valid_category(cur, body.category_id)
        cur.execute(
            "INSERT INTO budgets (category_id, monthly_amount) VALUES (%s, %s) "
            "ON CONFLICT (category_id) DO UPDATE SET monthly_amount = EXCLUDED.monthly_amount, deleted_at = NULL "
            "RETURNING id",
            (body.category_id, body.monthly_amount))
        new_id = cur.fetchone()[0]
    return {"id": new_id}


@router.delete("/{budget_id}")
def delete_budget(budget_id: int):
    with db_transaction() as cur:
        cur.execute("SELECT category_id FROM budgets WHERE id = %s AND deleted_at IS NULL", (budget_id,))
        old = cur.fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Budget not found")
        cur.execute("UPDATE budgets SET deleted_at = NOW() WHERE id = %s", (budget_id,))
        _audit(cur, "budget", budget_id, "soft_delete", field_name="category_id", old_value=old[0])
    return {"status": "ok"}


@router.get("/status")
def budget_status(start_date: Optional[date] = None, end_date: Optional[date] = None):
    now = datetime.now()
    if not start_date:
        start_date = date(now.year, now.month, 1)
    if not end_date:
        end_date = (date(now.year, 12, 31) if now.month == 12
                    else date(now.year, now.month + 1, 1) - timedelta(days=1))
    with db_read() as cur:
        cur.execute(
            "SELECT b.id, b.category_id, c.name, c.color, c.group_name, b.monthly_amount "
            "FROM budgets b JOIN categories c ON b.category_id = c.id "
            "WHERE b.deleted_at IS NULL AND c.deleted_at IS NULL ORDER BY c.sort_order, c.name")
        budgets = cur.fetchall()
        if not budgets:
            return {"budgets": [], "period": {"start": start_date.isoformat(), "end": end_date.isoformat()}}
        cur.execute(
            "SELECT t.category_id, SUM(ABS(t.amount)) "
            "FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
            "AND t.posted >= %s AND t.posted <= %s GROUP BY t.category_id",
            (start_date, end_date))
        actuals = {r[0]: float(r[1]) for r in cur.fetchall()}
    tb = ts = 0
    results = []
    for b in budgets:
        ba = float(b[5]); sp = actuals.get(b[1], 0); tb += ba; ts += sp
        results.append({"budget_id": b[0], "category_id": b[1], "category": b[2], "color": b[3],
                        "group": b[4], "budget": ba, "spent": sp, "remaining": ba - sp,
                        "pct": round((sp / ba * 100) if ba > 0 else 0, 1)})
    return {"budgets": results,
            "totals": {"budget": tb, "spent": ts, "remaining": tb - ts,
                       "pct": round((ts / tb * 100) if tb > 0 else 0, 1)},
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()}}
