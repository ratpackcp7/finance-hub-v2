"""Savings goals router — CRUD, progress tracking, snapshots."""
import math
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_read, db_transaction

router = APIRouter(prefix="/api/goals", tags=["goals"])

GOAL_TYPES = {"emergency_fund", "savings", "debt_payoff", "purchase", "custom"}


@router.get("")
def list_goals(status: Optional[str] = None):
    """List all savings goals with computed progress."""
    with db_read() as cur:
        filters = ["1=1"]
        params = []
        if status:
            filters.append("g.status = %s")
            params.append(status)
        cur.execute(
            f"""SELECT g.id, g.name, g.target_amount, g.current_amount, g.account_id,
                       a.name, a.balance, g.goal_type, g.target_date,
                       g.monthly_contribution, g.color, g.notes, g.status,
                       g.completed_at, g.created_at
                FROM savings_goals g
                LEFT JOIN accounts a ON g.account_id = a.id
                WHERE {' AND '.join(filters)}
                ORDER BY g.status ASC, g.created_at DESC""", params)
        rows = cur.fetchall()

    goals = []
    for r in rows:
        target = float(r[2])
        # If linked to account, use account balance as current amount
        if r[4] and r[6] is not None:
            current = float(r[6])
        else:
            current = float(r[3]) if r[3] else 0

        pct = (current / target * 100) if target > 0 else 0
        remaining = max(0, target - current)

        # Estimate months to goal
        months_est = None
        if r[9] and float(r[9]) > 0 and remaining > 0:
            months_est = math.ceil(remaining / float(r[9]))
        elif r[8] and remaining > 0:
            days_left = (r[8] - date.today()).days
            months_est = max(1, math.ceil(days_left / 30)) if days_left > 0 else 0

        goals.append({
            "id": r[0], "name": r[1], "target_amount": target,
            "current_amount": round(current, 2),
            "account_id": r[4], "account_name": r[5],
            "goal_type": r[7], "target_date": r[8].isoformat() if r[8] else None,
            "monthly_contribution": float(r[9]) if r[9] else None,
            "color": r[10] or "#3b82f6", "notes": r[11],
            "status": r[12],
            "completed_at": r[13].isoformat() if r[13] else None,
            "pct": round(min(pct, 100), 1),
            "remaining": round(remaining, 2),
            "months_to_goal": months_est,
        })
    return goals


class GoalCreate(BaseModel):
    name: str
    target_amount: float
    current_amount: Optional[float] = 0
    account_id: Optional[str] = None
    goal_type: str = "savings"
    target_date: Optional[str] = None
    monthly_contribution: Optional[float] = None
    color: Optional[str] = "#3b82f6"
    notes: Optional[str] = None


@router.post("", status_code=201)
def create_goal(body: GoalCreate):
    if body.target_amount <= 0:
        raise HTTPException(status_code=400, detail="target_amount must be positive")
    if body.goal_type not in GOAL_TYPES:
        raise HTTPException(status_code=400, detail=f"goal_type must be one of: {', '.join(sorted(GOAL_TYPES))}")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    with db_transaction() as cur:
        if body.account_id:
            cur.execute("SELECT id FROM accounts WHERE id = %s", (body.account_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail="Account not found")
        cur.execute(
            "INSERT INTO savings_goals (name, target_amount, current_amount, account_id, "
            "goal_type, target_date, monthly_contribution, color, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (name, body.target_amount, body.current_amount or 0, body.account_id,
             body.goal_type, body.target_date, body.monthly_contribution,
             body.color, body.notes))
        goal_id = cur.fetchone()[0]
    return {"id": goal_id, "name": name}


class GoalUpdate(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[float] = None
    current_amount: Optional[float] = None
    account_id: Optional[str] = None
    goal_type: Optional[str] = None
    target_date: Optional[str] = None
    monthly_contribution: Optional[float] = None
    color: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


@router.patch("/{goal_id}")
def update_goal(goal_id: int, body: GoalUpdate):
    with db_transaction() as cur:
        cur.execute("SELECT id FROM savings_goals WHERE id = %s", (goal_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Goal not found")

        updates = []
        params = []
        for field in ["name", "target_amount", "current_amount", "account_id",
                       "goal_type", "target_date", "monthly_contribution",
                       "color", "notes", "status"]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{field} = %s")
                params.append(val)

        if body.status == "completed":
            updates.append("completed_at = NOW()")

        if not updates:
            return {"status": "no-op"}

        updates.append("updated_at = NOW()")
        params.append(goal_id)
        cur.execute(f"UPDATE savings_goals SET {', '.join(updates)} WHERE id = %s", params)
    return {"status": "ok"}


@router.delete("/{goal_id}")
def delete_goal(goal_id: int):
    with db_transaction() as cur:
        cur.execute("DELETE FROM goal_snapshots WHERE goal_id = %s", (goal_id,))
        cur.execute("DELETE FROM savings_goals WHERE id = %s", (goal_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Goal not found")
    return {"status": "ok"}


class GoalContribution(BaseModel):
    amount: float
    notes: Optional[str] = None


@router.post("/{goal_id}/contribute")
def add_contribution(goal_id: int, body: GoalContribution):
    """Add a manual contribution to a non-account-linked goal."""
    with db_transaction() as cur:
        cur.execute("SELECT current_amount, account_id, target_amount FROM savings_goals WHERE id = %s", (goal_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Goal not found")
        if row[1]:
            raise HTTPException(status_code=400, detail="This goal is linked to an account — balance is tracked automatically")

        new_amount = float(row[0]) + body.amount
        status = "completed" if new_amount >= float(row[2]) else "active"
        cur.execute(
            "UPDATE savings_goals SET current_amount = %s, status = %s, "
            "completed_at = CASE WHEN %s = 'completed' THEN NOW() ELSE completed_at END, "
            "updated_at = NOW() WHERE id = %s",
            (new_amount, status, status, goal_id))
        _audit(cur, "goal", goal_id, "contribution", source="user",
               field_name="current_amount", old_value=str(row[0]), new_value=str(new_amount))
    return {"status": "ok", "current_amount": round(new_amount, 2),
            "goal_status": status}


@router.get("/summary")
def goals_summary():
    """Quick summary for dashboard."""
    with db_read() as cur:
        cur.execute(
            """SELECT g.id, g.name, g.target_amount, g.current_amount, g.account_id,
                      a.balance, g.goal_type, g.color, g.status
               FROM savings_goals g
               LEFT JOIN accounts a ON g.account_id = a.id
               WHERE g.status = 'active'
               ORDER BY g.created_at""")
        rows = cur.fetchall()

    goals = []
    for r in rows:
        target = float(r[2])
        current = float(r[5]) if r[4] and r[5] is not None else float(r[3] or 0)
        pct = (current / target * 100) if target > 0 else 0
        goals.append({
            "id": r[0], "name": r[1], "target": target,
            "current": round(current, 2), "pct": round(min(pct, 100), 1),
            "type": r[6], "color": r[7],
        })
    return {"goals": goals, "count": len(goals)}
