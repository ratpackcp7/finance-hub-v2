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


def _parse_category_filter(raw: Optional[str]) -> tuple[Optional[int], bool]:
    """Parse category_id query param: None/'' = no filter, 'none' = uncategorized, int = specific."""
    if raw in (None, ""):
        return None, False
    if raw == "none":
        return None, True
    try:
        return int(raw), False
    except ValueError:
        raise HTTPException(status_code=400, detail="category_id must be an integer or 'none'")


def _txn_filters(account_id=None, category_id=None, start_date=None, end_date=None,
                 search=None, pending=None, exclude_transfers=False, txn_type=None,
                 uncategorized=False, recurring=None):
    filters, params = [], []
    if account_id:
        filters.append("t.account_id = %s"); params.append(account_id)
    if uncategorized:
        filters.append("t.category_id IS NULL")
    elif category_id is not None:
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
    elif txn_type == "income":
        filters.append("t.amount > 0")
        filters.append("c.is_income = TRUE")
    elif txn_type == "spending":
        filters.append("t.amount < 0")
        filters.append("COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer')")
    if recurring is not None:
        filters.append("t.recurring = %s"); params.append(recurring)
    return filters, params


@router.get("/transactions")
def get_transactions(limit: int = 200, offset: int = 0, account_id: Optional[str] = None,
                     category_id: Optional[str] = None, start_date: Optional[date] = None,
                     end_date: Optional[date] = None, search: Optional[str] = None,
                     pending: Optional[bool] = None, txn_type: Optional[str] = None,
                     recurring: Optional[bool] = None,
                     exclude_transfers: Optional[bool] = None,
                     tag_id: Optional[int] = None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        parsed_category_id, uncategorized = _parse_category_filter(category_id)
        filters, params = _txn_filters(
            account_id, parsed_category_id, start_date, end_date, search, pending,
            txn_type=txn_type, uncategorized=uncategorized, recurring=recurring,
            exclude_transfers=exclude_transfers or False
        )
        # Tag filter: join transaction_tags if filtering by tag
        tag_join = ""
        if tag_id is not None:
            tag_join = "JOIN transaction_tags tt ON t.id = tt.txn_id"
            filters.append("tt.tag_id = %s")
            params.append(tag_id)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        if account_id:
            cur.execute(
                f"""WITH bal AS (SELECT id, SUM(amount) OVER (ORDER BY posted ASC, id ASC) AS running_balance
                        FROM transactions WHERE account_id = %s)
                    SELECT t.id, t.account_id, a.name, t.posted, t.amount, t.description, t.payee,
                           t.category_id, c.name, t.category_manual, t.pending, t.notes, t.is_transfer,
                           t.category_source, bal.running_balance, t.recurring, t.transfer_pair_id, t.source, t.has_splits, t.reconciled_at
                    FROM transactions t JOIN accounts a ON t.account_id = a.id
                    LEFT JOIN categories c ON t.category_id = c.id
                    LEFT JOIN bal ON t.id = bal.id {tag_join} {where}
                    ORDER BY t.posted DESC, t.id LIMIT %s OFFSET %s""",
                [account_id] + params + [limit, offset])
        else:
            cur.execute(
                f"""SELECT t.id, t.account_id, a.name, t.posted, t.amount, t.description, t.payee,
                           t.category_id, c.name, t.category_manual, t.pending, t.notes, t.is_transfer,
                           t.category_source, NULL as running_balance, t.recurring, t.transfer_pair_id, t.source, t.has_splits, t.reconciled_at
                    FROM transactions t JOIN accounts a ON t.account_id = a.id
                    LEFT JOIN categories c ON t.category_id = c.id {tag_join} {where}
                    ORDER BY t.posted DESC, t.id LIMIT %s OFFSET %s""",
                params + [limit, offset])
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*), COALESCE(SUM(t.amount), 0) FROM transactions t LEFT JOIN categories c ON t.category_id = c.id {tag_join} {where}", params)
        count_row = cur.fetchone()
        total = count_row[0]
        total_amount = float(count_row[1])
    finally:
        db_put(conn)
    return {
        "total": total, "total_amount": total_amount, "limit": limit, "offset": offset, "has_balance": account_id is not None,
        "transactions": [
            {"id": r[0], "account_id": r[1], "account_name": r[2],
             "posted": r[3].isoformat() if r[3] else None,
             "amount": float(r[4]) if r[4] is not None else None,
             "description": r[5], "payee": r[6], "category_id": r[7], "category": r[8],
             "category_manual": r[9], "pending": r[10], "notes": r[11], "is_transfer": r[12],
             "category_source": r[13],
             "running_balance": float(r[14]) if r[14] is not None else None,
             "recurring": r[15] if len(r) > 15 else False,
             "transfer_pair_id": r[16] if len(r) > 16 else None,
             "source": r[17] if len(r) > 17 else "sync",
             "has_splits": r[18] if len(r) > 18 else False}
            for r in rows]}


@router.get("/transactions/export")
def export_transactions(account_id: Optional[str] = None, category_id: Optional[str] = None,
                        start_date: Optional[date] = None, end_date: Optional[date] = None,
                        search: Optional[str] = None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        parsed_category_id, uncategorized = _parse_category_filter(category_id)
        filters, params = _txn_filters(
            account_id, parsed_category_id, start_date, end_date, search,
            uncategorized=uncategorized
        )
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
    recurring: Optional[bool] = None


@router.patch("/transactions/{txn_id}")
def patch_transaction(txn_id: str, body: TxnPatch):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT category_id, payee, notes, reconciled_at FROM transactions WHERE id = %s", (txn_id,))
        old = cur.fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Transaction not found")
        if old[3] is not None:
            raise HTTPException(status_code=400, detail="Transaction is in a reconciled period. Unlock in Reconcile page first.")
        old_cat, old_payee, old_notes = old
        updates, params = [], []
        if "category_id" in body.model_fields_set:
            if body.category_id is None:
                updates += ["category_id = NULL", "category_manual = FALSE", "category_source = NULL"]
            else:
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
        if body.recurring is not None:
            updates.append("recurring = %s"); params.append(body.recurring)
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
        import hashlib as _hl
        for pair in body.pairs:
            pair_id = "xfer_" + _hl.sha256(":".join(sorted(pair)).encode()).hexdigest()[:16]
            for txn_id in pair:
                cur.execute(
                    "UPDATE transactions SET is_transfer = TRUE, transfer_pair_id = %s, updated_at = NOW() "
                    "WHERE id = %s AND is_transfer = FALSE", (pair_id, txn_id))
                if cur.rowcount:
                    _audit(cur, "transaction", txn_id, "mark_transfer", source="user",
                           field_name="is_transfer", old_value=False, new_value=True)
                    marked += 1
        conn.commit()
    finally:
        db_put(conn)
    return {"marked": marked}


# ── Manual Transaction Entry (Phase 1 MVP) ──

class ManualTxnCreate(BaseModel):
    account_id: str
    posted: date
    amount: float
    description: str
    payee: Optional[str] = None
    category_id: Optional[int] = None
    notes: Optional[str] = None
    is_transfer: bool = False


@router.post("/transactions")
def create_manual_transaction(body: ManualTxnCreate):
    """Create a manually entered transaction."""
    import hashlib
    from datetime import datetime

    if not body.description or not body.description.strip():
        raise HTTPException(status_code=400, detail="description is required")
    if not body.account_id:
        raise HTTPException(status_code=400, detail="account_id is required")

    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM accounts WHERE id = %s", (body.account_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Account not found")
        if body.category_id is not None:
            require_valid_category(cur, body.category_id)

        ts = datetime.utcnow().isoformat()
        txn_id = "manual_" + hashlib.sha256(
            f"{body.account_id}:{body.posted}:{body.amount:.2f}:{body.description}:{ts}".encode()
        ).hexdigest()[:20]

        cur.execute(
            """INSERT INTO transactions
               (id, account_id, posted, amount, description, payee,
                category_id, category_manual, category_source,
                notes, is_transfer, pending, source)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, 'manual')
               RETURNING id""",
            (txn_id, body.account_id, body.posted, body.amount,
             body.description.strip(), (body.payee or "").strip() or None,
             body.category_id, body.category_id is not None,
             'user' if body.category_id else None,
             (body.notes or "").strip() or None, body.is_transfer))

        _audit(cur, "transaction", txn_id, "manual_create", source="user",
               field_name="amount", new_value=f"{body.amount:.2f}")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_put(conn)
    return {"status": "ok", "id": txn_id}


@router.delete("/transactions/{txn_id}")
def delete_manual_transaction(txn_id: str):
    """Delete a manually entered transaction. Only manual transactions can be deleted."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT source, amount, description FROM transactions WHERE id = %s", (txn_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Transaction not found")
        if row[0] != 'manual':
            raise HTTPException(status_code=400, detail="Only manually entered transactions can be deleted")
        cur.execute("DELETE FROM transactions WHERE id = %s", (txn_id,))
        _audit(cur, "transaction", txn_id, "manual_delete", source="user",
               field_name="amount", old_value=f"{row[1]:.2f}")
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok"}


# ── Transfer Pair Linking (Phase 1 MVP) ──

class TransferLinkRequest(BaseModel):
    txn_id_1: str
    txn_id_2: str


@router.post("/transfers/link")
def link_transfer_pair(body: TransferLinkRequest):
    """Link two transactions as a transfer pair."""
    import hashlib

    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, account_id, amount FROM transactions WHERE id IN (%s, %s)",
                    (body.txn_id_1, body.txn_id_2))
        rows = cur.fetchall()
        if len(rows) != 2:
            raise HTTPException(status_code=404, detail="One or both transactions not found")
        accts = {r[0]: r[1] for r in rows}
        if accts[body.txn_id_1] == accts[body.txn_id_2]:
            raise HTTPException(status_code=400, detail="Transfer pairs must be in different accounts")

        pair_id = "xfer_" + hashlib.sha256(
            f"{body.txn_id_1}:{body.txn_id_2}".encode()
        ).hexdigest()[:16]

        for txn_id in (body.txn_id_1, body.txn_id_2):
            cur.execute(
                "UPDATE transactions SET is_transfer = TRUE, transfer_pair_id = %s, updated_at = NOW() "
                "WHERE id = %s", (pair_id, txn_id))
            _audit(cur, "transaction", txn_id, "link_transfer", source="user",
                   field_name="transfer_pair_id", new_value=pair_id)
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "pair_id": pair_id}


@router.delete("/transfers/link/{pair_id}")
def unlink_transfer_pair(pair_id: str):
    """Unlink a transfer pair."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE transactions SET is_transfer = FALSE, transfer_pair_id = NULL, updated_at = NOW() "
            "WHERE transfer_pair_id = %s", (pair_id,))
        count = cur.rowcount
        if count == 0:
            raise HTTPException(status_code=404, detail="Transfer pair not found")
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "unlinked": count}
