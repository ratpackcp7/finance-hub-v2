"""Bulk operations router — batch category, tag, review, delete for multiple transactions."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_conn, db_put, require_valid_category

router = APIRouter(prefix="/api/bulk", tags=["bulk"])


class BulkCategorize(BaseModel):
    txn_ids: list[str]
    category_id: Optional[int] = None  # None = clear category


@router.post("/categorize")
def bulk_categorize(body: BulkCategorize):
    """Batch-apply a category to multiple transactions."""
    if not body.txn_ids:
        raise HTTPException(status_code=400, detail="txn_ids required")
    conn = db_conn()
    try:
        cur = conn.cursor()
        if body.category_id is not None:
            require_valid_category(cur, body.category_id)

        updated = 0
        for txn_id in body.txn_ids:
            cur.execute("SELECT reconciled_at FROM transactions WHERE id = %s", (txn_id,))
            row = cur.fetchone()
            if not row:
                continue
            if row[0] is not None:
                continue  # Skip reconciled
            if body.category_id is not None:
                cur.execute(
                    "UPDATE transactions SET category_id = %s, category_manual = TRUE, "
                    "category_source = 'user', updated_at = NOW() WHERE id = %s",
                    (body.category_id, txn_id))
            else:
                cur.execute(
                    "UPDATE transactions SET category_id = NULL, category_manual = FALSE, "
                    "category_source = NULL, updated_at = NOW() WHERE id = %s",
                    (txn_id,))
            updated += 1
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "updated": updated}


class BulkTag(BaseModel):
    txn_ids: list[str]
    tag_id: int
    action: str = "add"  # add or remove


@router.post("/tag")
def bulk_tag(body: BulkTag):
    """Batch add or remove a tag on multiple transactions."""
    if not body.txn_ids:
        raise HTTPException(status_code=400, detail="txn_ids required")
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM tags WHERE id = %s", (body.tag_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="Tag not found")

        count = 0
        for txn_id in body.txn_ids:
            if body.action == "add":
                cur.execute(
                    "INSERT INTO transaction_tags (txn_id, tag_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING", (txn_id, body.tag_id))
            else:
                cur.execute(
                    "DELETE FROM transaction_tags WHERE txn_id = %s AND tag_id = %s",
                    (txn_id, body.tag_id))
            count += cur.rowcount
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "affected": count}


class BulkReview(BaseModel):
    txn_ids: list[str]


@router.post("/mark-reviewed")
def bulk_mark_reviewed(body: BulkReview):
    """Batch mark transactions as reviewed."""
    if not body.txn_ids:
        raise HTTPException(status_code=400, detail="txn_ids required")
    conn = db_conn()
    try:
        cur = conn.cursor()
        updated = 0
        for txn_id in body.txn_ids:
            cur.execute(
                "UPDATE transactions SET reviewed_at = NOW(), updated_at = NOW() "
                "WHERE id = %s AND reviewed_at IS NULL", (txn_id,))
            updated += cur.rowcount
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "reviewed": updated}


class BulkTransfer(BaseModel):
    txn_ids: list[str]
    is_transfer: bool


@router.post("/transfer")
def bulk_set_transfer(body: BulkTransfer):
    """Batch mark/unmark transactions as transfers."""
    if not body.txn_ids:
        raise HTTPException(status_code=400, detail="txn_ids required")
    conn = db_conn()
    try:
        cur = conn.cursor()
        updated = 0
        for txn_id in body.txn_ids:
            cur.execute(
                "UPDATE transactions SET is_transfer = %s, updated_at = NOW() WHERE id = %s",
                (body.is_transfer, txn_id))
            updated += cur.rowcount
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "updated": updated}
