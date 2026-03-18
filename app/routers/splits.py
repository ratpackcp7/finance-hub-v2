"""Transaction splits router — split one txn across multiple categories."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_conn, db_put, require_valid_category

router = APIRouter(prefix="/api/splits", tags=["splits"])


class SplitItem(BaseModel):
    category_id: Optional[int] = None
    amount: float
    description: Optional[str] = None


class SplitRequest(BaseModel):
    txn_id: str
    splits: list[SplitItem]


@router.get("/{txn_id}")
def get_splits(txn_id: str):
    """Get all splits for a transaction."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM transactions WHERE id = %s", (txn_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Transaction not found")
        cur.execute(
            "SELECT s.id, s.category_id, c.name, c.color, s.amount, s.description "
            "FROM transaction_splits s LEFT JOIN categories c ON s.category_id = c.id "
            "WHERE s.txn_id = %s ORDER BY s.id", (txn_id,))
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "category_id": r[1], "category": r[2], "color": r[3],
             "amount": float(r[4]), "description": r[5]} for r in rows]


@router.post("")
def set_splits(body: SplitRequest):
    """Set splits for a transaction. Replaces any existing splits.
    Split amounts must sum to the transaction amount."""
    if len(body.splits) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 splits")

    conn = db_conn()
    try:
        cur = conn.cursor()

        # Get parent transaction
        cur.execute("SELECT amount, account_id FROM transactions WHERE id = %s", (body.txn_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Transaction not found")
        parent_amount = float(row[0])

        # Validate split sum matches parent
        split_sum = sum(s.amount for s in body.splits)
        if abs(split_sum - parent_amount) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=f"Splits sum ({split_sum:.2f}) must equal transaction amount ({parent_amount:.2f})")

        # Validate categories
        for s in body.splits:
            if s.category_id is not None:
                require_valid_category(cur, s.category_id)

        # Delete old splits
        cur.execute("DELETE FROM transaction_splits WHERE txn_id = %s", (body.txn_id,))

        # Insert new splits
        for s in body.splits:
            cur.execute(
                "INSERT INTO transaction_splits (txn_id, category_id, amount, description) "
                "VALUES (%s, %s, %s, %s)",
                (body.txn_id, s.category_id, s.amount, (s.description or "").strip() or None))

        # Mark parent as split
        cur.execute(
            "UPDATE transactions SET has_splits = TRUE, updated_at = NOW() WHERE id = %s",
            (body.txn_id,))

        _audit(cur, "transaction", body.txn_id, "split_set", source="user",
               field_name="splits", new_value=f"{len(body.splits)} splits")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_put(conn)
    return {"status": "ok", "splits": len(body.splits)}


@router.delete("/{txn_id}")
def remove_splits(txn_id: str):
    """Remove all splits from a transaction, reverting to single-category."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM transaction_splits WHERE txn_id = %s", (txn_id,))
        deleted = cur.rowcount
        cur.execute(
            "UPDATE transactions SET has_splits = FALSE, updated_at = NOW() WHERE id = %s",
            (txn_id,))
        _audit(cur, "transaction", txn_id, "split_remove", source="user",
               field_name="splits", old_value=f"{deleted} splits")
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "removed": deleted}
