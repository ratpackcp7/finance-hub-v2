"""Review queue router — triage unreviewed/uncategorized transactions."""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_read, db_transaction

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/queue")
def review_queue(limit: int = 50, filter_type: Optional[str] = None):
    """Get transactions needing review, sorted by priority.
    filter_type: uncategorized | ai | recent | large | all (default)
    """
    with db_read() as cur:
        now = datetime.now()
        cutoff_recent = (now - timedelta(hours=48)).date()

        # Build priority-sorted union query
        # Priority 1: Uncategorized
        # Priority 2: AI-categorized (may need confirmation)
        # Priority 3: Recently imported (last 48h, not reviewed)
        # Priority 4: Large amounts (>$500, not reviewed)

        if filter_type == "uncategorized":
            where = "t.category_id IS NULL AND t.pending = FALSE AND t.is_transfer = FALSE"
        elif filter_type == "ai":
            where = "t.category_source = 'ai' AND t.reviewed_at IS NULL AND t.pending = FALSE"
        elif filter_type == "recent":
            where = f"t.posted >= '{cutoff_recent}' AND t.reviewed_at IS NULL AND t.pending = FALSE"
        elif filter_type == "large":
            where = "ABS(t.amount) >= 500 AND t.reviewed_at IS NULL AND t.pending = FALSE AND t.is_transfer = FALSE"
        else:
            # All items needing attention
            where = (
                "t.pending = FALSE AND ("
                "  (t.category_id IS NULL AND t.is_transfer = FALSE) OR "
                "  (t.category_source = 'ai' AND t.reviewed_at IS NULL) OR "
                f"  (t.posted >= '{cutoff_recent}' AND t.reviewed_at IS NULL) OR "
                "  (ABS(t.amount) >= 500 AND t.reviewed_at IS NULL AND t.is_transfer = FALSE)"
                ")"
            )

        cur.execute(
            f"""SELECT t.id, t.account_id, a.name, t.posted, t.amount, t.description,
                       t.payee, t.category_id, c.name, t.category_source, t.is_transfer,
                       t.reviewed_at, t.source, t.has_splits, t.recurring,
                       CASE
                         WHEN t.category_id IS NULL AND t.is_transfer = FALSE THEN 1
                         WHEN t.category_source = 'ai' AND t.reviewed_at IS NULL THEN 2
                         WHEN t.posted >= %s AND t.reviewed_at IS NULL THEN 3
                         WHEN ABS(t.amount) >= 500 AND t.reviewed_at IS NULL THEN 4
                         ELSE 5
                       END as priority
                FROM transactions t
                JOIN accounts a ON t.account_id = a.id
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE {where}
                ORDER BY priority ASC, t.posted DESC
                LIMIT %s""",
            (cutoff_recent, limit))
        rows = cur.fetchall()

        # Counts per type
        cur.execute("SELECT COUNT(*) FROM transactions WHERE category_id IS NULL AND pending = FALSE AND is_transfer = FALSE")
        ct_uncat = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM transactions WHERE category_source = 'ai' AND reviewed_at IS NULL AND pending = FALSE")
        ct_ai = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM transactions WHERE posted >= %s AND reviewed_at IS NULL AND pending = FALSE", (cutoff_recent,))
        ct_recent = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM transactions WHERE ABS(amount) >= 500 AND reviewed_at IS NULL AND pending = FALSE AND is_transfer = FALSE")
        ct_large = cur.fetchone()[0]

    items = []
    for r in rows:
        reason = []
        if r[7] is None and not r[10]:
            reason.append("uncategorized")
        if r[9] == "ai" and r[11] is None:
            reason.append("ai-assigned")
        if r[3] and r[3] >= cutoff_recent and r[11] is None:
            reason.append("recent")
        if abs(float(r[4])) >= 500 and r[11] is None and not r[10]:
            reason.append("large")

        items.append({
            "id": r[0], "account_id": r[1], "account_name": r[2],
            "posted": r[3].isoformat() if r[3] else None,
            "amount": float(r[4]), "description": r[5], "payee": r[6],
            "category_id": r[7], "category": r[8],
            "category_source": r[9], "is_transfer": r[10],
            "reviewed_at": r[11].isoformat() if r[11] else None,
            "source": r[12], "has_splits": r[13], "recurring": r[14],
            "priority": r[15], "reasons": reason,
        })

    return {
        "items": items,
        "counts": {
            "uncategorized": ct_uncat,
            "ai_assigned": ct_ai,
            "recent": ct_recent,
            "large": ct_large,
            "total": ct_uncat + ct_ai,  # Primary action items
        },
    }


class MarkReviewedRequest(BaseModel):
    txn_ids: list[str]


@router.post("/mark-reviewed")
def mark_reviewed(body: MarkReviewedRequest):
    """Batch mark transactions as reviewed."""
    if not body.txn_ids:
        raise HTTPException(status_code=400, detail="txn_ids required")
    with db_transaction() as cur:
        updated = 0
        for txn_id in body.txn_ids:
            cur.execute(
                "UPDATE transactions SET reviewed_at = NOW(), updated_at = NOW() "
                "WHERE id = %s AND reviewed_at IS NULL", (txn_id,))
            updated += cur.rowcount
    return {"status": "ok", "reviewed": updated}


@router.post("/mark-all-reviewed")
def mark_all_reviewed():
    """Mark ALL unreviewed, categorized, non-pending transactions as reviewed."""
    with db_transaction() as cur:
        cur.execute(
            "UPDATE transactions SET reviewed_at = NOW(), updated_at = NOW() "
            "WHERE reviewed_at IS NULL AND category_id IS NOT NULL "
            "AND pending = FALSE AND is_transfer = FALSE")
        count = cur.rowcount
    return {"status": "ok", "reviewed": count}


@router.get("/counts")
def review_counts():
    """Quick counts for dashboard badge."""
    with db_read() as cur:
        cur.execute("SELECT COUNT(*) FROM transactions WHERE category_id IS NULL AND pending = FALSE AND is_transfer = FALSE")
        uncat = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM transactions WHERE category_source = 'ai' AND reviewed_at IS NULL AND pending = FALSE")
        ai = cur.fetchone()[0]
    return {"uncategorized": uncat, "ai_unreviewed": ai, "total": uncat + ai}
