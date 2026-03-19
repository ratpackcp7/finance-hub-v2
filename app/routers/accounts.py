"""Accounts router — CRUD, net worth, snapshots."""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import ACCOUNT_TYPES, _audit, db_read, db_transaction

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/accounts")
def get_accounts():
    with db_read() as cur:
        cur.execute(
            "SELECT id, name, org_name, currency, balance, balance_date, on_budget, hidden, updated_at, account_type, payment_due_day, minimum_payment, apr, credit_limit, autopay_enabled, loan_rate, loan_term_months, loan_payment, loan_maturity_date "
            "FROM accounts WHERE hidden = FALSE ORDER BY org_name, name")
        rows = cur.fetchall()
    return [{"id": r[0], "name": r[1], "org": r[2], "currency": r[3],
             "balance": float(r[4]) if r[4] is not None else None,
             "balance_date": r[5].isoformat() if r[5] else None,
             "on_budget": r[6], "hidden": r[7],
             "updated_at": r[8].isoformat() if r[8] else None,
             "account_type": r[9] or "checking", "on_budget": r[6],
             "payment_due_day": r[10], "minimum_payment": float(r[11]) if r[11] is not None else None,
             "apr": float(r[12]) if r[12] is not None else None,
             "credit_limit": float(r[13]) if r[13] is not None else None,
             "autopay_enabled": r[14] or False,
             "loan_rate": float(r[15]) if r[15] is not None else None,
             "loan_term_months": r[16],
             "loan_payment": float(r[17]) if r[17] is not None else None,
             "loan_maturity_date": r[18].isoformat() if r[18] else None} for r in rows]


class AccountPatch(BaseModel):
    account_type: Optional[str] = None
    on_budget: Optional[bool] = None
    payment_due_day: Optional[int] = None
    minimum_payment: Optional[float] = None
    apr: Optional[float] = None
    credit_limit: Optional[float] = None
    autopay_enabled: Optional[bool] = None
    loan_rate: Optional[float] = None
    loan_term_months: Optional[int] = None
    loan_payment: Optional[float] = None
    loan_maturity_date: Optional[str] = None


@router.patch("/accounts/{acct_id}")
def patch_account(acct_id: str, body: AccountPatch):
    if body.account_type and body.account_type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"account_type must be one of: {', '.join(sorted(ACCOUNT_TYPES))}")
    with db_transaction() as cur:
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

        # Credit card / loan metadata
        meta_fields = {
            "payment_due_day": body.payment_due_day,
            "minimum_payment": body.minimum_payment,
            "apr": body.apr,
            "credit_limit": body.credit_limit,
            "autopay_enabled": body.autopay_enabled,
            "loan_rate": body.loan_rate,
            "loan_term_months": body.loan_term_months,
            "loan_payment": body.loan_payment,
            "loan_maturity_date": body.loan_maturity_date,
        }
        for field, value in meta_fields.items():
            if value is not None:
                cur.execute(f"SELECT {field} FROM accounts WHERE id = %s", (acct_id,))
                old_val = cur.fetchone()
                cur.execute(f"UPDATE accounts SET {field} = %s, updated_at = NOW() WHERE id = %s",
                            (value, acct_id))
                _audit(cur, "account", acct_id, "update", field_name=field,
                       old_value=str(old_val[0]) if old_val and old_val[0] is not None else None,
                       new_value=str(value))
    return {"status": "ok"}


@router.get("/accounts/net-worth")
def net_worth():
    with db_read() as cur:
        cur.execute(
            "SELECT COALESCE(account_type, 'checking'), SUM(balance), COUNT(*) "
            "FROM accounts WHERE hidden = FALSE AND on_budget = TRUE AND balance IS NOT NULL GROUP BY 1 ORDER BY 1")
        rows = cur.fetchall()
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
    return count


@router.post("/snapshots/take")
def take_snapshot():
    with db_transaction() as cur:
        count = _take_snapshot(cur)
    return {"status": "ok", "accounts": count, "date": date.today().isoformat()}



@router.get("/net-worth/breakdown")
def net_worth_breakdown():
    """Net worth grouped by account type with individual accounts."""
    with db_read() as cur:
        cur.execute(
            "SELECT id, name, COALESCE(account_type, 'checking'), balance, on_budget "
            "FROM accounts WHERE hidden = FALSE AND balance IS NOT NULL ORDER BY account_type, balance DESC")
        rows = cur.fetchall()
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
    with db_read() as cur:
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
    total_debt = sum(abs(a["balance"]) for a in result)
    return {"accounts": result, "total_debt": total_debt}


@router.get("/investments/history")
def investment_history(months: int = 12):
    """Per-account balance history for investment/retirement/brokerage accounts."""
    with db_read() as cur:
        cutoff = date.today() - timedelta(days=months * 31)
        cur.execute(
            "SELECT bs.snapshot_date, bs.account_id, bs.account_name, bs.account_type, bs.balance "
            "FROM balance_snapshots bs "
            "JOIN accounts a ON a.id = bs.account_id "
            "WHERE a.account_type IN ('investment', 'retirement', 'brokerage') "
            "AND a.hidden = FALSE AND bs.snapshot_date >= %s "
            "ORDER BY bs.snapshot_date ASC", (cutoff,))
        rows = cur.fetchall()
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
    with db_read() as cur:
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


@router.get("/investment/performance")
def investment_performance(months: int = 0):
    """Monthly investment performance from Vanguard data."""
    with db_read() as cur:
        if months > 0:
            cutoff = date.today() - timedelta(days=months * 31)
            cur.execute(
                "SELECT month, beginning_balance, deposits_withdrawals, market_gain_loss, "
                "income_returns, personal_investment_returns, cumulative_returns, ending_balance "
                "FROM investment_performance WHERE month >= %s ORDER BY month ASC", (cutoff,))
        else:
            cur.execute(
                "SELECT month, beginning_balance, deposits_withdrawals, market_gain_loss, "
                "income_returns, personal_investment_returns, cumulative_returns, ending_balance "
                "FROM investment_performance ORDER BY month ASC")
        rows = cur.fetchall()
    records = []
    for r in rows:
        records.append({
            "month": r[0].isoformat()[:7],
            "beginning_balance": float(r[1]) if r[1] else 0,
            "deposits": float(r[2]) if r[2] else 0,
            "market_gain_loss": float(r[3]) if r[3] else 0,
            "income_returns": float(r[4]) if r[4] else 0,
            "personal_returns": float(r[5]) if r[5] else 0,
            "cumulative_returns": float(r[6]) if r[6] else 0,
            "ending_balance": float(r[7]) if r[7] else 0,
        })
    # Summary stats
    total_deposits = sum(r["deposits"] for r in records)
    total_returns = records[-1]["cumulative_returns"] if records else 0
    total_income = sum(r["income_returns"] for r in records)
    return {
        "records": records,
        "summary": {
            "total_deposits": total_deposits,
            "total_returns": total_returns,
            "total_income": total_income,
            "months": len(records),
            "start": records[0]["month"] if records else None,
            "end": records[-1]["month"] if records else None,
            "rate_of_return": total_returns if total_returns else None
        }
    }

@router.get("/net-worth/history")
def net_worth_history(months: int = 12):
    with db_read() as cur:
        cutoff = date.today() - timedelta(days=months * 31)
        cur.execute(
            "SELECT snapshot_date, COALESCE(account_type, 'checking'), SUM(balance) "
            "FROM balance_snapshots WHERE snapshot_date >= %s "
            "GROUP BY snapshot_date, account_type ORDER BY snapshot_date ASC", (cutoff,))
        rows = cur.fetchall()
    by_date = {}
    for snap_date, acct_type, total in rows:
        d = snap_date.isoformat()
        if d not in by_date:
            by_date[d] = {"date": d, "groups": {}, "net_worth": 0}
        by_date[d]["groups"][acct_type] = float(total)
        by_date[d]["net_worth"] += float(total)
    return {"history": sorted(by_date.values(), key=lambda x: x["date"]), "months": months}
