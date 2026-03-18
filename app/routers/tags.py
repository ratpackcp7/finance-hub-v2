"""Tags router — CRUD for tags + transaction tag assignments."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_conn, db_put

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("")
def list_tags():
    """List all tags with usage counts."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT t.id, t.name, t.color, COUNT(tt.txn_id) as usage_count "
            "FROM tags t LEFT JOIN transaction_tags tt ON t.id = tt.tag_id "
            "GROUP BY t.id, t.name, t.color ORDER BY t.name")
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "name": r[1], "color": r[2], "count": r[3]} for r in rows]


class TagCreate(BaseModel):
    name: str
    color: Optional[str] = "#64748b"


@router.post("", status_code=201)
def create_tag(body: TagCreate):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tags (name, color) VALUES (%s, %s) "
            "ON CONFLICT (name) DO UPDATE SET color = EXCLUDED.color RETURNING id",
            (name, body.color or "#64748b"))
        tag_id = cur.fetchone()[0]
        conn.commit()
    finally:
        db_put(conn)
    return {"id": tag_id, "name": name}


@router.delete("/{tag_id}")
def delete_tag(tag_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM transaction_tags WHERE tag_id = %s", (tag_id,))
        cur.execute("DELETE FROM tags WHERE id = %s", (tag_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Tag not found")
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok"}


# ── Transaction tagging ──

@router.get("/transaction/{txn_id}")
def get_txn_tags(txn_id: str):
    """Get all tags for a transaction."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT t.id, t.name, t.color FROM tags t "
            "JOIN transaction_tags tt ON t.id = tt.tag_id "
            "WHERE tt.txn_id = %s ORDER BY t.name", (txn_id,))
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "name": r[1], "color": r[2]} for r in rows]


class TagAssign(BaseModel):
    txn_id: str
    tag_ids: list[int]


@router.post("/assign")
def assign_tags(body: TagAssign):
    """Set tags on a transaction. Replaces existing tags."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM transactions WHERE id = %s", (body.txn_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Transaction not found")

        # Remove old tags
        cur.execute("DELETE FROM transaction_tags WHERE txn_id = %s", (body.txn_id,))

        # Assign new tags
        for tag_id in body.tag_ids:
            cur.execute("SELECT id FROM tags WHERE id = %s", (tag_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail=f"Tag {tag_id} not found")
            cur.execute(
                "INSERT INTO transaction_tags (txn_id, tag_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (body.txn_id, tag_id))

        _audit(cur, "transaction", body.txn_id, "tags_set", source="user",
               field_name="tags", new_value=str(body.tag_ids))
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "tags": len(body.tag_ids)}


@router.post("/toggle")
def toggle_tag(txn_id: str, tag_id: int):
    """Toggle a single tag on/off for a transaction."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM transactions WHERE id = %s", (txn_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Transaction not found")
        cur.execute(
            "SELECT 1 FROM transaction_tags WHERE txn_id = %s AND tag_id = %s",
            (txn_id, tag_id))
        if cur.fetchone():
            cur.execute(
                "DELETE FROM transaction_tags WHERE txn_id = %s AND tag_id = %s",
                (txn_id, tag_id))
            action = "removed"
        else:
            cur.execute(
                "INSERT INTO transaction_tags (txn_id, tag_id) VALUES (%s, %s)",
                (txn_id, tag_id))
            action = "added"
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "action": action}
