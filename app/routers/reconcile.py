"""Reconciliation workflow router.

Flow:
  1. Create session: pick account + enter statement date + statement balance
  2. Show uncleared transactions for that account up to statement date
  3. User marks transactions as cleared (checkbox)
  4. App calculates: sum(cleared txns) vs statement_balance → difference
  5. When difference = 0, user can complete the session
  6. Completing marks all cleared txns as reconciled
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_conn, db_put

router = APIRouter(prefix="/api/reconcile", tags=["reconcile"])


# ── Sessions ──

class ReconCreateRequest(BaseModel):
    account_id: str
    statement_date: date
    statement_balance: float
    notes: Optional[str] = None


@router.post("/sessions")
def create_session(body: ReconCreateRequest):
    conn = db_conn()
    try:
        cur = conn.cursor()
        # Verify account
        cur.execute("SELECT id, name FROM accounts WHERE id = %s", (body.account_id,))
        acct = cur.fetchone()
        if not acct:
            raise HTTPException(status_code=400, detail="Account not found")
        # Check no open session for this account
        cur.execute(
            "SELECT id FROM reconciliation_sessions WHERE account_id = %s AND status = 'open'",
            (body.account_id,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="An open reconciliation session already exists for this account")
        cur.execute(
            "INSERT INTO reconciliation_sessions (account_id, statement_date, statement_balance, notes) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (body.account_id, body.statement_date, body.statement_balance, body.notes))
        session_id = cur.fetchone()[0]
        conn.commit()
    finally:
        db_put(conn)
    return {"id": session_id, "account_id": body.account_id, "status": "open"}


@router.get("/sessions")
def list_sessions(account_id: Optional[str] = None, status: Optional[str] = None, limit: int = 20):
    conn = db_conn()
    try:
        cur = conn.cursor()
        filters, params = [], []
        if account_id:
            filters.append("s.account_id = %s"); params.append(account_id)
        if status:
            filters.append("s.status = %s"); params.append(status)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        cur.execute(
            f"""SELECT s.id, s.account_id, a.name, s.statement_date, s.statement_balance,
                       s.status, s.cleared_count, s.cleared_balance, s.difference,
                       s.started_at, s.completed_at, s.notes
                FROM reconciliation_sessions s
                JOIN accounts a ON s.account_id = a.id
                {where} ORDER BY s.id DESC LIMIT %s""",
            params + [limit])
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "account_id": r[1], "account_name": r[2],
             "statement_date": r[3].isoformat() if r[3] else None,
             "statement_balance": float(r[4]) if r[4] is not None else 0,
             "status": r[5], "cleared_count": r[6],
             "cleared_balance": float(r[7]) if r[7] is not None else 0,
             "difference": float(r[8]) if r[8] is not None else 0,
             "started_at": r[9].isoformat() if r[9] else None,
             "completed_at": r[10].isoformat() if r[10] else None,
             "notes": r[11]} for r in rows]


@router.get("/sessions/{session_id}")
def get_session(session_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT s.id, s.account_id, a.name, s.statement_date, s.statement_balance,
                      s.status, s.cleared_count, s.cleared_balance, s.difference,
                      s.started_at, s.completed_at, s.notes
               FROM reconciliation_sessions s
               JOIN accounts a ON s.account_id = a.id
               WHERE s.id = %s""", (session_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get uncleared transactions for this account up to statement date
        cur.execute(
            """SELECT t.id, t.posted, t.amount, t.description, t.payee,
                      t.category_id, c.name as category, t.cleared, t.is_transfer, t.pending
               FROM transactions t
               LEFT JOIN categories c ON t.category_id = c.id
               WHERE t.account_id = %s AND t.posted <= %s
                 AND t.reconciled_at IS NULL AND t.pending = FALSE
               ORDER BY t.posted ASC, t.id""",
            (r[1], r[3]))
        txns = [{"id": t[0], "posted": t[1].isoformat() if t[1] else None,
                 "amount": float(t[2]) if t[2] is not None else 0,
                 "description": t[3], "payee": t[4],
                 "category_id": t[5], "category": t[6],
                 "cleared": t[7], "is_transfer": t[8], "pending": t[9]}
                for t in cur.fetchall()]

        # Recalculate cleared totals
        cleared_txns = [t for t in txns if t["cleared"]]
        cleared_balance = sum(t["amount"] for t in cleared_txns)
        difference = float(r[4]) - cleared_balance

        # Update session with current totals
        cur.execute(
            "UPDATE reconciliation_sessions SET cleared_count = %s, cleared_balance = %s, difference = %s "
            "WHERE id = %s",
            (len(cleared_txns), cleared_balance, difference, session_id))
        conn.commit()
    finally:
        db_put(conn)

    return {
        "id": r[0], "account_id": r[1], "account_name": r[2],
        "statement_date": r[3].isoformat() if r[3] else None,
        "statement_balance": float(r[4]) if r[4] is not None else 0,
        "status": r[5],
        "cleared_count": len(cleared_txns),
        "cleared_balance": cleared_balance,
        "difference": difference,
        "started_at": r[9].isoformat() if r[9] else None,
        "completed_at": r[10].isoformat() if r[10] else None,
        "notes": r[11],
        "transactions": txns,
    }


# ── Toggle cleared ──

class ClearToggleRequest(BaseModel):
    txn_ids: list[str]
    cleared: bool


@router.post("/sessions/{session_id}/clear")
def toggle_cleared(session_id: int, body: ClearToggleRequest):
    conn = db_conn()
    try:
        cur = conn.cursor()
        # Verify session is open
        cur.execute("SELECT status, account_id FROM reconciliation_sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        if row[0] != "open":
            raise HTTPException(status_code=400, detail="Session is not open")

        updated = 0
        for txn_id in body.txn_ids:
            cur.execute(
                "UPDATE transactions SET cleared = %s, updated_at = NOW() "
                "WHERE id = %s AND account_id = %s AND reconciled_at IS NULL",
                (body.cleared, txn_id, row[1]))
            if cur.rowcount:
                updated += 1
                _audit(cur, "transaction", txn_id, "reconcile_clear", source="user",
                       field_name="cleared", new_value=body.cleared)
        conn.commit()
    finally:
        db_put(conn)
    return {"updated": updated}


# ── Complete session ──

@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status, account_id, statement_date, statement_balance "
            "FROM reconciliation_sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        if row[0] != "open":
            raise HTTPException(status_code=400, detail="Session is not open")

        account_id, stmt_date, stmt_balance = row[1], row[2], float(row[3])

        # Calculate cleared balance
        cur.execute(
            "SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM transactions "
            "WHERE account_id = %s AND posted <= %s AND cleared = TRUE AND reconciled_at IS NULL",
            (account_id, stmt_date))
        cleared_sum, cleared_count = cur.fetchone()
        cleared_sum = float(cleared_sum)
        difference = stmt_balance - cleared_sum

        if abs(difference) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot complete: difference is ${difference:.2f}. "
                       f"Statement balance: ${stmt_balance:.2f}, cleared: ${cleared_sum:.2f}")

        # Mark all cleared txns as reconciled
        cur.execute(
            "UPDATE transactions SET reconciled_at = NOW(), updated_at = NOW() "
            "WHERE account_id = %s AND posted <= %s AND cleared = TRUE AND reconciled_at IS NULL",
            (account_id, stmt_date))
        reconciled = cur.rowcount

        # Close session
        cur.execute(
            "UPDATE reconciliation_sessions SET status = 'completed', completed_at = NOW(), "
            "cleared_count = %s, cleared_balance = %s, difference = %s "
            "WHERE id = %s",
            (cleared_count, cleared_sum, 0, session_id))
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "completed", "reconciled": reconciled}


# ── Abandon session ──

@router.post("/sessions/{session_id}/abandon")
def abandon_session(session_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status, account_id, statement_date FROM reconciliation_sessions WHERE id = %s",
                    (session_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        if row[0] != "open":
            raise HTTPException(status_code=400, detail="Session is not open")

        # Uncheck all cleared txns for this session's scope
        cur.execute(
            "UPDATE transactions SET cleared = FALSE, updated_at = NOW() "
            "WHERE account_id = %s AND posted <= %s AND cleared = TRUE AND reconciled_at IS NULL",
            (row[1], row[2]))

        cur.execute(
            "UPDATE reconciliation_sessions SET status = 'abandoned', completed_at = NOW() WHERE id = %s",
            (session_id,))
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "abandoned"}
