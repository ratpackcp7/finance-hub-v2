"""Accounts router — CRUD, net worth, snapshots."""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import ACCOUNT_TYPES, _audit, db_conn, db_put

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/accounts")
def get_accounts():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, org_name, currency, balance, balance_date, on_budget, hidden, updated_at, account_type "
            "FROM accounts WHERE hidden = FALSE ORDER BY org_name, name")
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "name": r[1], "org": r[2], "currency": r[3],
             "balance": float(r[4]) if r[4] is not None else None,
             "balance_date": r[5].isoformat() if r[5] else None,
             "on_budget": r[6], "hidden": r[7],
             "updated_at": r[8].isoformat() if r[8] else None,
             "account_type": r[9] or "checking"} for r in rows]


class AccountPatch(BaseModel):
    account_type: Optional[str] = None


@router.patch("/accounts/{acct_id}")
def patch_account(acct_id: str, body: AccountPatch):
    if body.account_type and body.account_type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"account_type must be one of: {', '.join(sorted(ACCOUNT_TYPES))}")
    conn = db_conn()
    try:
        cur = conn.cursor()
        if body.account_type is not None:
            cur.execute("SELECT account_type FROM accounts WHERE id = %s", (acct_id,))
            old = cur.fetchone()
            if not old:
                raise HTTPException(status_code=404, detail="Account not found")
            cur.execute("UPDATE accounts SET account_type = %s, updated_at = NOW() WHERE id = %s",
                        (body.account_type, acct_id))
            _audit(cur, "account", acct_id, "update", field_name="account_type",
                   old_value=old[0], new_value=body.account_type)
            conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok"}


@router.get("/accounts/net-worth")
def net_worth():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(account_type, 'checking'), SUM(balance), COUNT(*) "
            "FROM accounts WHERE hidden = FALSE AND balance IS NOT NULL GROUP BY 1 ORDER BY 1")
        rows = cur.fetchall()
    finally:
        db_put(conn)
    groups = [{"type": r[0], "total": float(r[1]), "count": r[2]} for r in rows]
    return {"groups": groups, "net_worth": sum(g["total"] for g in groups)}


def _take_snapshot(conn):
    cur = conn.cursor()
    today = date.today()
    cur.execute(
        """INSERT INTO balance_snapshots (snapshot_date, account_id, account_name, account_type, balance)
           SELECT %s, id, name, COALESCE(account_type, 'checking'), balance
           FROM accounts WHERE hidden = FALSE AND balance IS NOT NULL
           ON CONFLICT (snapshot_date, account_id) DO UPDATE SET
             balance = EXCLUDED.balance, account_name = EXCLUDED.account_name, account_type = EXCLUDED.account_type""",
        (today,))
    count = cur.rowcount
    conn.commit()
    return count


@router.post("/snapshots/take")
def take_snapshot():
    conn = db_conn()
    try:
        count = _take_snapshot(conn)
    finally:
        db_put(conn)
    return {"status": "ok", "accounts": count, "date": date.today().isoformat()}


@router.get("/net-worth/history")
def net_worth_history(months: int = 12):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cutoff = date.today() - timedelta(days=months * 31)
        cur.execute(
            "SELECT snapshot_date, COALESCE(account_type, 'checking'), SUM(balance) "
            "FROM balance_snapshots WHERE snapshot_date >= %s "
            "GROUP BY snapshot_date, account_type ORDER BY snapshot_date ASC", (cutoff,))
        rows = cur.fetchall()
    finally:
        db_put(conn)
    by_date = {}
    for snap_date, acct_type, total in rows:
        d = snap_date.isoformat()
        if d not in by_date:
            by_date[d] = {"date": d, "groups": {}, "net_worth": 0}
        by_date[d]["groups"][acct_type] = float(total)
        by_date[d]["net_worth"] += float(total)
    return {"history": sorted(by_date.values(), key=lambda x: x["date"]), "months": months}
