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
             "account_type": r[9] or "checking", "on_budget": r[6]} for r in rows]


class AccountPatch(BaseModel):
    account_type: Optional[str] = None
    on_budget: Optional[bool] = None


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
        if body.on_budget is not None:
            cur.execute("SELECT on_budget FROM accounts WHERE id = %s", (acct_id,))
            old_ob = cur.fetchone()
            cur.execute("UPDATE accounts SET on_budget = %s, updated_at = NOW() WHERE id = %s",
                        (body.on_budget, acct_id))
            _audit(cur, "account", acct_id, "update", field_name="on_budget",
                   old_value=str(old_ob[0]) if old_ob else None, new_value=str(body.on_budget))
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
            "FROM accounts WHERE hidden = FALSE AND on_budget = TRUE AND balance IS NOT NULL GROUP BY 1 ORDER BY 1")
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



@router.get("/net-worth/breakdown")
def net_worth_breakdown():
    """Net worth grouped by account type with individual accounts."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, COALESCE(account_type, 'checking'), balance, on_budget "
            "FROM accounts WHERE hidden = FALSE AND balance IS NOT NULL ORDER BY account_type, balance DESC")
        rows = cur.fetchall()
    finally:
        db_put(conn)
    groups = {}
    for r in rows:
        atype = r[2]
        if atype not in groups:
            groups[atype] = {"type": atype, "total": 0, "accounts": []}
        acct = {"id": r[0], "name": r[1], "balance": float(r[3]), "on_budget": r[4]}
        groups[atype]["total"] += float(r[3])
        groups[atype]["accounts"].append(acct)
    return {"groups": sorted(groups.values(), key=lambda g: -abs(g["total"]))}


@router.get("/debt/summary")
def debt_summary():
    """Loan accounts with payment history for payoff tracking."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        # Get loan/mortgage accounts
        cur.execute(
            "SELECT id, name, COALESCE(account_type, 'checking'), balance "
            "FROM accounts WHERE hidden = FALSE AND account_type IN ('loan', 'mortgage') "
            "ORDER BY balance ASC")
        accts = cur.fetchall()
        
        # Get balance snapshots for these accounts
        result = []
        for a in accts:
            cur.execute(
                "SELECT snapshot_date, balance FROM balance_snapshots "
                "WHERE account_id = %s ORDER BY snapshot_date ASC", (a[0],))
            snaps = cur.fetchall()
            result.append({
                "id": a[0], "name": a[1], "type": a[2],
                "balance": float(a[3]),
                "history": [{"date": s[0].isoformat(), "balance": float(s[1])} for s in snaps]
            })
    finally:
        db_put(conn)
    total_debt = sum(abs(a["balance"]) for a in result)
    return {"accounts": result, "total_debt": total_debt}


@router.get("/investments/history")
def investment_history(months: int = 12):
    """Per-account balance history for investment/retirement/brokerage accounts."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cutoff = date.today() - timedelta(days=months * 31)
        cur.execute(
            "SELECT bs.snapshot_date, bs.account_id, bs.account_name, bs.account_type, bs.balance "
            "FROM balance_snapshots bs "
            "JOIN accounts a ON a.id = bs.account_id "
            "WHERE a.account_type IN ('investment', 'retirement', 'brokerage') "
            "AND a.hidden = FALSE AND bs.snapshot_date >= %s "
            "ORDER BY bs.snapshot_date ASC", (cutoff,))
        rows = cur.fetchall()
    finally:
        db_put(conn)
    # Group by account
    by_acct = {}
    for snap_date, acct_id, acct_name, acct_type, balance in rows:
        if acct_id not in by_acct:
            by_acct[acct_id] = {"id": acct_id, "name": acct_name, "type": acct_type, "history": []}
        by_acct[acct_id]["history"].append({"date": snap_date.isoformat(), "balance": float(balance)})
    return {"accounts": list(by_acct.values())}


@router.get("/dividends/summary")
def dividend_summary():
    """Dividend income from investment accounts."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        # Positive transactions in investment/retirement/brokerage accounts
        # that represent real income (not reinvestment pairs)
        cur.execute("""
            SELECT DATE_TRUNC('month', t.posted)::date AS month,
                   t.payee, a.name AS account_name, SUM(t.amount) AS total
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE a.account_type IN ('investment', 'retirement', 'brokerage')
            AND t.amount > 0
                        GROUP BY 1, 2, 3
            ORDER BY 1 DESC, 4 DESC
        """)
        rows = cur.fetchall()
    finally:
        db_put(conn)
    entries = []
    monthly_totals = {}
    for month, payee, acct, total in rows:
        m = month.isoformat()[:7]
        entries.append({"month": m, "payee": payee, "account": acct, "amount": float(total)})
        monthly_totals[m] = monthly_totals.get(m, 0) + float(total)
    return {
        "entries": entries,
        "monthly_totals": [{"month": m, "total": t} for m, t in sorted(monthly_totals.items())]
    }

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
