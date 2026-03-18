"""Transactions router — list, patch, export, transfers."""
import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db import MAX_TEXT_LEN, _audit, _csv_safe, db_conn, db_put, require_valid_category

router = APIRouter(prefix="/api", tags=["transactions"])


def _txn_filters(account_id=None, category_id=None, start_date=None, end_date=None,
                 search=None, pending=None, exclude_transfers=False, txn_type=None):
    filters, params = [], []
    if account_id:
        filters.append("t.account_id = %s"); params.append(account_id)
    if category_id is not None:
        filters.append("t.category_id = %s"); params.append(category_id)
    if start_date:
        filters.append("t.posted >= %s"); params.append(start_date)
    if end_date:
        filters.append("t.posted <= %s"); params.append(end_date)
    if search:
        filters.append("(lower(t.description) LIKE %s OR lower(t.payee) LIKE %s)")
        params += [f"%{search.lower()}%", f"%{search.lower()}%"]
    if pending is not None:
        filters.append("t.pending = %s"); params.append(pending)
    if exclude_transfers:
        filters.append("t.is_transfer = FALSE")
    if txn_type == "debit":
        filters.append("t.amount < 0")
    elif txn_type == "credit":
        filters.append("t.amount > 0")
    return filters, params


@router.get("/transactions")
def get_transactions(limit: int = 200, offset: int = 0, account_id: Optional[str] = None,
                     category_id: Optional[int] = None, start_date: Optional[date] = None,
                     end_date: Optional[date] = None, search: Optional[str] = None,
                     pending: Optional[bool] = None, txn_type: Optional[str] = None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        filters, params = _txn_filters(account_id, category_id, start_date, end_date, search, pending, txn_type=txn_type)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        if account_id:
            cur.execute(
                f"""WITH bal AS (SELECT id, SUM(amount) OVER (ORDER BY posted ASC, id ASC) AS running_balance
                        FROM transactions WHERE account_id = %s)
                    SELECT t.id, t.account_id, a.name, t.posted, t.amount, t.description, t.payee,
                           t.category_id, c.name, t.category_manual, t.pending, t.notes, t.is_transfer,
                           t.category_source, bal.running_balance
                    FROM transactions t JOIN accounts a ON t.account_id = a.id
                    LEFT JOIN categories c ON t.category_id = c.id
                    LEFT JOIN bal ON t.id = bal.id {where}
                    ORDER BY t.posted DESC, t.id LIMIT %s OFFSET %s""",
                [account_id] + params + [limit, offset])
        else:
            cur.execute(
                f"""SELECT t.id, t.account_id, a.name, t.posted, t.amount, t.description, t.payee,
                           t.category_id, c.name, t.category_manual, t.pending, t.notes, t.is_transfer,
                           t.category_source, NULL as running_balance
                    FROM transactions t JOIN accounts a ON t.account_id = a.id
                    LEFT JOIN categories c ON t.category_id = c.id {where}
                    ORDER BY t.posted DESC, t.id LIMIT %s OFFSET %s""",
                params + [limit, offset])
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*) FROM transactions t {where}", params)
        total = cur.fetchone()[0]
    finally:
        db_put(conn)
    return {
        "total": total, "limit": limit, "offset": offset, "has_balance": account_id is not None,
        "transactions": [
            {"id": r[0], "account_id": r[1], "account_name": r[2],
             "posted": r[3].isoformat() if r[3] else None,
             "amount": float(r[4]) if r[4] is not None else None,
             "description": r[5], "payee": r[6], "category_id": r[7], "category": r[8],
             "category_manual": r[9], "pending": r[10], "notes": r[11], "is_transfer": r[12],
             "category_source": r[13],
             "running_balance": float(r[14]) if r[14] is not None else None}
            for r in rows]}


@router.get("/transactions/export")
def export_transactions(account_id: Optional[str] = None, category_id: Optional[int] = None,
                        start_date: Optional[date] = None, end_date: Optional[date] = None,
                        search: Optional[str] = None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        filters, params = _txn_filters(account_id, category_id, start_date, end_date, search)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        cur.execute(
            f"""SELECT t.posted, COALESCE(t.payee, t.description, ''), t.description, a.name,
                       COALESCE(c.name, 'Uncategorized'), t.amount, t.is_transfer, t.notes,
                       t.category_source
                FROM transactions t JOIN accounts a ON t.account_id = a.id
                LEFT JOIN categories c ON t.category_id = c.id {where}
                ORDER BY t.posted DESC, t.id""", params)
        rows = cur.fetchall()
    finally:
        db_put(conn)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Payee", "Description", "Account", "Category", "Amount", "Transfer", "Notes", "Category Source"])
    for r in rows:
        w.writerow([r[0].isoformat() if r[0] else "", _csv_safe(r[1]), _csv_safe(r[2]),
                    _csv_safe(r[3]), _csv_safe(r[4]),
                    f"{float(r[5]):.2f}" if r[5] is not None else "",
                    "Yes" if r[6] else "", _csv_safe(r[7] or ""),
                    _csv_safe(r[8] or "")])
    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="finance_hub_{date.today().isoformat()}.csv"'})


class TxnPatch(BaseModel):
    category_id: Optional[int] = None
    payee: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/transactions/{txn_id}")
def patch_transaction(txn_id: str, body: TxnPatch):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT category_id, payee, notes FROM transactions WHERE id = %s", (txn_id,))
        old = cur.fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Transaction not found")
        old_cat, old_payee, old_notes = old
        updates, params = [], []
        if body.category_id is not None:
            require_valid_category(cur, body.category_id)
            updates += ["category_id = %s", "category_manual = TRUE", "category_source = 'user'"]
            params.append(body.category_id)
            _audit(cur, "transaction", txn_id, "update", source="user", field_name="category_id",
                   old_value=old_cat, new_value=body.category_id)
        if body.payee is not None:
            if len(body.payee) > MAX_TEXT_LEN:
                raise HTTPException(status_code=400, detail=f"payee exceeds max length ({MAX_TEXT_LEN})")
            updates.append("payee = %s"); params.append(body.payee)
            _audit(cur, "transaction", txn_id, "update", field_name="payee",
                   old_value=old_payee, new_value=body.payee)
        if body.notes is not None:
            if len(body.notes) > MAX_TEXT_LEN:
                raise HTTPException(status_code=400, detail=f"notes exceeds max length ({MAX_TEXT_LEN})")
            updates.append("notes = %s"); params.append(body.notes)
            _audit(cur, "transaction", txn_id, "update", field_name="notes",
                   old_value=old_notes, new_value=body.notes)
        if not updates:
            return {"status": "no-op"}
        updates.append("updated_at = NOW()"); params.append(txn_id)
        cur.execute(f"UPDATE transactions SET {', '.join(updates)} WHERE id = %s", params)
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok"}


# ── Transfer Detection ──

@router.patch("/transactions/{txn_id}/transfer")
def toggle_transfer(txn_id: str):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_transfer FROM transactions WHERE id = %s", (txn_id,))
        old = cur.fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Transaction not found")
        cur.execute(
            "UPDATE transactions SET is_transfer = NOT is_transfer, updated_at = NOW() "
            "WHERE id = %s RETURNING is_transfer", (txn_id,))
        new_val = cur.fetchone()[0]
        _audit(cur, "transaction", txn_id, "toggle_transfer", field_name="is_transfer",
               old_value=old[0], new_value=new_val)
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "is_transfer": new_val}


@router.post("/transfers/detect")
def detect_transfers(days_window: int = 3, amount_tolerance: float = 0.01):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT t1.id, t1.account_id, a1.name, t1.posted, t1.amount, t1.description,
                      t2.id, t2.account_id, a2.name, t2.posted, t2.amount, t2.description
               FROM transactions t1 JOIN transactions t2 ON t1.id < t2.id
               JOIN accounts a1 ON t1.account_id = a1.id JOIN accounts a2 ON t2.account_id = a2.id
               WHERE t1.account_id != t2.account_id
                 AND t1.is_transfer = FALSE AND t2.is_transfer = FALSE
                 AND t1.pending = FALSE AND t2.pending = FALSE
                 AND ABS(t1.amount + t2.amount) <= %s AND ABS(t1.posted - t2.posted) <= %s
               ORDER BY t1.posted DESC LIMIT 200""",
            (amount_tolerance, days_window))
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"txn1": {"id": r[0], "account_id": r[1], "account_name": r[2],
                      "posted": r[3].isoformat() if r[3] else None, "amount": float(r[4]), "description": r[5]},
             "txn2": {"id": r[6], "account_id": r[7], "account_name": r[8],
                      "posted": r[9].isoformat() if r[9] else None, "amount": float(r[10]), "description": r[11]}}
            for r in rows]


class TransferApplyRequest(BaseModel):
    pairs: list[list[str]]


@router.post("/transfers/apply")
def apply_transfers(body: TransferApplyRequest):
    conn = db_conn()
    marked = 0
    try:
        cur = conn.cursor()
        for pair in body.pairs:
            for txn_id in pair:
                cur.execute(
                    "UPDATE transactions SET is_transfer = TRUE, updated_at = NOW() "
                    "WHERE id = %s AND is_transfer = FALSE", (txn_id,))
                if cur.rowcount:
                    _audit(cur, "transaction", txn_id, "mark_transfer", source="user",
                           field_name="is_transfer", old_value=False, new_value=True)
                    marked += 1
        conn.commit()
    finally:
        db_put(conn)
    return {"marked": marked}
