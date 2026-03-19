"""Bills & Debt router — upcoming bills, debt payoff scenarios."""
import math
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from db import db_read, db_transaction

router = APIRouter(prefix="/api", tags=["bills"])


# ══════════════════════════════════════
# UPCOMING BILLS
# ══════════════════════════════════════

@router.get("/bills/upcoming")
def upcoming_bills(days: int = 30):
    """Get upcoming bills from recurring transactions + CC/loan due dates.
    Combines two sources:
    1. Recurring transactions with predicted next occurrence
    2. Account due dates (CC payment_due_day, loan payment)
    """
    today = date.today()
    horizon = today + timedelta(days=days)
    with db_read() as cur:
        bills = []

        # Source 1: Account due dates (credit cards + loans)
        cur.execute(
            "SELECT id, name, account_type, balance, payment_due_day, "
            "minimum_payment, loan_payment, autopay_enabled, next_due_date "
            "FROM accounts WHERE hidden = FALSE AND ("
            "  (account_type = 'credit' AND payment_due_day IS NOT NULL) OR "
            "  (account_type IN ('loan', 'mortgage') AND loan_payment IS NOT NULL) OR "
            "  next_due_date IS NOT NULL"
            ")")
        for row in cur.fetchall():
            acct_id, name, atype, balance, due_day, min_pay, loan_pay, autopay, next_due = row

            # Calculate next due date
            if next_due and next_due >= today:
                ndd = next_due
            elif due_day:
                ndd = date(today.year, today.month, min(due_day, 28))
                if ndd < today:
                    m = today.month + 1
                    y = today.year + (1 if m > 12 else 0)
                    m = m if m <= 12 else m - 12
                    ndd = date(y, m, min(due_day, 28))
            else:
                continue

            if ndd > horizon:
                continue

            amount = float(loan_pay) if loan_pay else (float(min_pay) if min_pay else None)
            bills.append({
                "source": "account",
                "name": name,
                "account_id": acct_id,
                "account_type": atype,
                "due_date": ndd.isoformat(),
                "amount": amount,
                "balance": float(balance) if balance is not None else None,
                "autopay": bool(autopay),
                "days_until": (ndd - today).days,
                "overdue": ndd < today,
            })

        # Source 2: Recurring transactions (predicted next occurrence)
        cur.execute(
            """WITH recent_recurring AS (
                SELECT COALESCE(t.payee, t.description) as payee,
                       t.account_id, a.name as account_name,
                       MAX(t.posted) as last_date,
                       AVG(ABS(t.amount)) as avg_amount,
                       COUNT(*) as occurrences
                FROM transactions t
                JOIN accounts a ON t.account_id = a.id
                WHERE t.recurring = TRUE AND t.pending = FALSE
                AND t.posted >= %s
                GROUP BY COALESCE(t.payee, t.description), t.account_id, a.name
                HAVING COUNT(*) >= 2
            )
            SELECT payee, account_id, account_name, last_date, avg_amount, occurrences
            FROM recent_recurring ORDER BY last_date DESC""",
            (today - timedelta(days=180),))

        for payee, acct_id, acct_name, last_date, avg_amt, count in cur.fetchall():
            # Predict next occurrence (~30 days after last)
            predicted = last_date + timedelta(days=30)
            if predicted < today - timedelta(days=7):
                # Already overdue by more than a week — push to next month
                predicted = date(today.year, today.month, predicted.day if predicted.day <= 28 else 28)
                if predicted < today:
                    m = today.month + 1
                    y = today.year + (1 if m > 12 else 0)
                    m = m if m <= 12 else m - 12
                    predicted = date(y, m, min(predicted.day, 28))

            if predicted > horizon:
                continue

            bills.append({
                "source": "recurring",
                "name": payee or "Unknown",
                "account_id": acct_id,
                "account_name": acct_name,
                "due_date": predicted.isoformat(),
                "amount": -round(float(avg_amt), 2),
                "occurrences": count,
                "last_date": last_date.isoformat(),
                "days_until": (predicted - today).days,
                "overdue": predicted < today,
            })

    # Sort by due date
    bills.sort(key=lambda b: b["due_date"])

    total = sum(abs(b["amount"]) for b in bills if b.get("amount"))
    return {
        "bills": bills,
        "total_upcoming": round(total, 2),
        "count": len(bills),
        "horizon_days": days,
    }


# ══════════════════════════════════════
# DEBT PAYOFF CALCULATOR
# ══════════════════════════════════════

class DebtPayoffRequest(BaseModel):
    extra_monthly: float = 0
    strategy: str = "avalanche"  # avalanche (highest rate first) or snowball (lowest balance first)


@router.get("/debt/payoff")
def debt_payoff_scenarios(extra_monthly: float = 0, strategy: str = "avalanche"):
    """Calculate debt payoff timeline using snowball or avalanche method.
    Uses loan metadata from accounts table."""
    with db_read() as cur:
        cur.execute(
            "SELECT id, name, account_type, ABS(balance), "
            "COALESCE(loan_rate, apr, 0), COALESCE(loan_payment, minimum_payment, 0) "
            "FROM accounts "
            "WHERE hidden = FALSE AND balance < 0 "
            "AND account_type IN ('credit', 'loan', 'mortgage') "
            "ORDER BY ABS(balance) ASC")
        rows = cur.fetchall()

    if not rows:
        return {"debts": [], "strategy": strategy, "message": "No debts found"}

    debts = []
    for acct_id, name, atype, balance, rate, payment in rows:
        debts.append({
            "id": acct_id,
            "name": name,
            "type": atype,
            "balance": float(balance),
            "rate": float(rate),
            "monthly_rate": float(rate) / 100 / 12 if rate else 0,
            "min_payment": float(payment) if payment else 0,
        })

    # Sort by strategy
    if strategy == "snowball":
        debts.sort(key=lambda d: d["balance"])
    else:  # avalanche
        debts.sort(key=lambda d: -d["rate"])

    # Simulate payoff
    total_balance = sum(d["balance"] for d in debts)
    total_min = sum(d["min_payment"] for d in debts)
    monthly_budget = total_min + extra_monthly

    if monthly_budget <= 0:
        return {
            "debts": [{
                "id": d["id"], "name": d["name"], "type": d["type"],
                "starting_balance": d["balance"], "rate": d["rate"],
                "min_payment": d["min_payment"],
                "paid_off_month": None, "paid_off_date": None,
            } for d in debts],
            "strategy": strategy,
            "extra_monthly": extra_monthly,
            "message": "No payment data — set minimum payments or loan payments on your accounts",
            "total_balance": total_balance,
            "total_min_payment": 0,
            "total_interest": 0,
            "months_to_payoff": None,
            "debt_free_date": None,
            "baseline_months": None,
            "months_saved": None,
        }

    # Simulate month by month
    sim = [{"balance": d["balance"], "paid_off_month": None} for d in debts]
    total_interest = 0
    month = 0
    max_months = 360  # 30 year cap

    while any(s["balance"] > 0.01 for s in sim) and month < max_months:
        month += 1
        remaining_extra = extra_monthly

        # Apply interest to all active debts
        for i, d in enumerate(debts):
            if sim[i]["balance"] <= 0.01:
                continue
            interest = sim[i]["balance"] * d["monthly_rate"]
            sim[i]["balance"] += interest
            total_interest += interest

        # Pay minimums on all active debts
        freed = 0
        for i, d in enumerate(debts):
            if sim[i]["balance"] <= 0.01:
                freed += d["min_payment"]
                continue
            payment = min(d["min_payment"], sim[i]["balance"])
            sim[i]["balance"] -= payment
            if sim[i]["balance"] <= 0.01:
                sim[i]["balance"] = 0
                sim[i]["paid_off_month"] = month
                freed += d["min_payment"] - payment

        # Apply extra + freed minimums to target debt
        extra_pool = remaining_extra + freed
        for i, d in enumerate(debts):
            if sim[i]["balance"] <= 0.01 or extra_pool <= 0:
                continue
            payment = min(extra_pool, sim[i]["balance"])
            sim[i]["balance"] -= payment
            extra_pool -= payment
            if sim[i]["balance"] <= 0.01:
                sim[i]["balance"] = 0
                sim[i]["paid_off_month"] = month

    # Build results
    results = []
    for i, d in enumerate(debts):
        results.append({
            "id": d["id"],
            "name": d["name"],
            "type": d["type"],
            "starting_balance": d["balance"],
            "rate": d["rate"],
            "min_payment": d["min_payment"],
            "paid_off_month": sim[i]["paid_off_month"],
            "paid_off_date": _add_months(date.today(), sim[i]["paid_off_month"]).isoformat() if sim[i]["paid_off_month"] else None,
        })

    debt_free_month = max((s["paid_off_month"] or max_months) for s in sim)
    debt_free_date = _add_months(date.today(), debt_free_month) if debt_free_month < max_months else None

    # Compare: what if no extra?
    baseline_months = _quick_payoff(debts, 0, strategy)

    return {
        "strategy": strategy,
        "extra_monthly": extra_monthly,
        "debts": results,
        "total_balance": round(total_balance, 2),
        "total_min_payment": round(total_min, 2),
        "total_interest": round(total_interest, 2),
        "months_to_payoff": debt_free_month if debt_free_month < max_months else None,
        "debt_free_date": debt_free_date.isoformat() if debt_free_date else None,
        "baseline_months": baseline_months,
        "months_saved": (baseline_months - debt_free_month) if baseline_months and debt_free_month < max_months else None,
    }


def _add_months(d: date, months: int) -> date:
    m = d.month + months
    y = d.year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return date(y, m, min(d.day, 28))


def _quick_payoff(debts, extra, strategy):
    """Quick simulation to get months to payoff."""
    sim = [d["balance"] for d in debts]
    total_min = sum(d["min_payment"] for d in debts)
    if total_min <= 0:
        return None
    month = 0
    while any(b > 0.01 for b in sim) and month < 360:
        month += 1
        freed = 0
        for i, d in enumerate(debts):
            if sim[i] <= 0.01:
                freed += d["min_payment"]
                continue
            sim[i] += sim[i] * d["monthly_rate"]
            pay = min(d["min_payment"], sim[i])
            sim[i] -= pay
            if sim[i] <= 0.01:
                sim[i] = 0
                freed += d["min_payment"] - pay
        # Apply freed to next target
        pool = extra + freed
        for i in range(len(debts)):
            if sim[i] <= 0.01 or pool <= 0:
                continue
            pay = min(pool, sim[i])
            sim[i] -= pay
            pool -= pay
    return month if month < 360 else None
