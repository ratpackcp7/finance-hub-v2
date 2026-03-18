"""Import batches + duplicate flags router."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_conn, db_put

router = APIRouter(prefix="/api", tags=["imports"])


@router.get("/import-batches")
def list_import_batches(limit: int = 20):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, started_at, finished_at, status, source, accounts_seen, txns_added, "
            "txns_updated, txns_skipped, dupes_flagged, error_message "
            "FROM import_batches ORDER BY id DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "started_at": r[1].isoformat() if r[1] else None,
             "finished_at": r[2].isoformat() if r[2] else None,
             "status": r[3], "source": r[4], "accounts_seen": r[5], "txns_added": r[6],
             "txns_updated": r[7], "txns_skipped": r[8], "dupes_flagged": r[9],
             "error_message": r[10]} for r in rows]


@router.get("/import-batches/{batch_id}")
def get_import_batch(batch_id: int, include_txns: bool = False):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, started_at, finished_at, status, source, accounts_seen, txns_added, "
            "txns_updated, txns_skipped, dupes_flagged, error_message "
            "FROM import_batches WHERE id = %s", (batch_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Batch not found")
        batch = {"id": row[0], "started_at": row[1].isoformat() if row[1] else None,
                 "finished_at": row[2].isoformat() if row[2] else None,
                 "status": row[3], "source": row[4], "accounts_seen": row[5], "txns_added": row[6],
                 "txns_updated": row[7], "txns_skipped": row[8], "dupes_flagged": row[9],
                 "error_message": row[10]}
        txns = []
        if include_txns:
            cur.execute(
                "SELECT t.id, t.account_id, a.name, t.posted, t.amount, t.description, t.payee, "
                "t.category_id, c.name, t.pending "
                "FROM transactions t JOIN accounts a ON t.account_id = a.id "
                "LEFT JOIN categories c ON t.category_id = c.id "
                "WHERE t.import_batch_id = %s ORDER BY t.posted DESC", (batch_id,))
            txns = [{"id": r[0], "account_id": r[1], "account_name": r[2],
                     "posted": r[3].isoformat() if r[3] else None,
                     "amount": float(r[4]) if r[4] else 0,
                     "description": r[5], "payee": r[6], "category_id": r[7],
                     "category": r[8], "pending": r[9]} for r in cur.fetchall()]
        cur.execute(
            "SELECT d.id, d.txn_id, d.duplicate_of, d.reason, d.status, d.created_at "
            "FROM duplicate_flags d WHERE d.batch_id = %s ORDER BY d.created_at", (batch_id,))
        dupes = [{"id": r[0], "txn_id": r[1], "duplicate_of": r[2], "reason": r[3],
                  "status": r[4], "created_at": r[5].isoformat() if r[5] else None}
                 for r in cur.fetchall()]
    finally:
        db_put(conn)
    batch["transactions"] = txns
    batch["duplicates"] = dupes
    return batch


# ── Duplicate Flags ──

@router.get("/duplicates")
def list_duplicates(status: Optional[str] = "pending", limit: int = 100):
    conn = db_conn()
    try:
        cur = conn.cursor()
        where = "WHERE d.status = %s" if status else ""
        params = [status] if status else []
        cur.execute(
            f"""SELECT d.id, d.txn_id, d.duplicate_of, d.reason, d.status, d.batch_id, d.created_at,
                       t1.posted, t1.amount, t1.description, t1.payee, a1.name,
                       t2.posted, t2.amount, t2.description, t2.payee, a2.name
                FROM duplicate_flags d
                LEFT JOIN transactions t1 ON d.txn_id = t1.id LEFT JOIN accounts a1 ON t1.account_id = a1.id
                LEFT JOIN transactions t2 ON d.duplicate_of = t2.id LEFT JOIN accounts a2 ON t2.account_id = a2.id
                {where} ORDER BY d.created_at DESC LIMIT %s""",
            params + [limit])
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "status": r[4], "batch_id": r[5],
             "created_at": r[6].isoformat() if r[6] else None, "reason": r[3],
             "new_txn": {"id": r[1], "posted": r[7].isoformat() if r[7] else None,
                         "amount": float(r[8]) if r[8] else 0, "description": r[9],
                         "payee": r[10], "account": r[11]},
             "existing_txn": {"id": r[2], "posted": r[12].isoformat() if r[12] else None,
                              "amount": float(r[13]) if r[13] else 0, "description": r[14],
                              "payee": r[15], "account": r[16]}} for r in rows]


class DupeResolveRequest(BaseModel):
    action: str


@router.post("/duplicates/{flag_id}/resolve")
def resolve_duplicate(flag_id: int, body: DupeResolveRequest):
    valid_actions = {"keep_both", "remove_new", "remove_existing"}
    if body.action not in valid_actions:
        raise HTTPException(status_code=400, detail="action must be one of: keep_both, remove_new, remove_existing")
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT txn_id, duplicate_of FROM duplicate_flags WHERE id = %s AND status = 'pending'",
                    (flag_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Flag not found or already resolved")
        new_txn_id, existing_txn_id = row
        if body.action == "remove_new":
            cur.execute("DELETE FROM transactions WHERE id = %s", (new_txn_id,))
            _audit(cur, "transaction", new_txn_id, "delete_as_duplicate", source="user",
                   field_name="duplicate_of", new_value=existing_txn_id)
        elif body.action == "remove_existing":
            cur.execute("DELETE FROM transactions WHERE id = %s", (existing_txn_id,))
            _audit(cur, "transaction", existing_txn_id, "delete_as_duplicate", source="user",
                   field_name="duplicate_of", new_value=new_txn_id)
        else:
            _audit(cur, "duplicate_flag", flag_id, "keep_both", source="user",
                   field_name="txn_ids", new_value=f"{new_txn_id},{existing_txn_id}")
        cur.execute("UPDATE duplicate_flags SET status = %s WHERE id = %s", (body.action, flag_id))
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "action": body.action}


@router.get("/duplicates/stats")
def duplicate_stats():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status, COUNT(*) FROM duplicate_flags GROUP BY status")
        rows = cur.fetchall()
    finally:
        db_put(conn)
    stats = {r[0]: r[1] for r in rows}
    return {"pending": stats.get("pending", 0), "keep_both": stats.get("keep_both", 0),
            "remove_new": stats.get("remove_new", 0), "remove_existing": stats.get("remove_existing", 0),
            "total": sum(stats.values())}
