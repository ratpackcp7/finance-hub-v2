"""Feedback router — CRUD with soft deletes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_conn, db_put

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackCreate(BaseModel):
    type: str = "feature"
    message: str


@router.post("", status_code=201)
def create_feedback(body: FeedbackCreate):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message required")
    valid = {"bug", "feature", "feedback"}
    fb_type = body.type if body.type in valid else "feedback"
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO feedback (type, message) VALUES (%s, %s) RETURNING id, created_at",
                    (fb_type, body.message.strip()))
        row = cur.fetchone()
        conn.commit()
    finally:
        db_put(conn)
    return {"id": row[0], "created_at": row[1].isoformat()}


@router.get("")
def get_feedback():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, type, message, created_at, notion_page_id "
            "FROM feedback WHERE deleted_at IS NULL ORDER BY created_at DESC")
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "type": r[1], "message": r[2], "created_at": r[3].isoformat(),
             "synced": r[4] is not None} for r in rows]


@router.delete("/{fb_id}")
def delete_feedback(fb_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE feedback SET deleted_at = NOW() WHERE id = %s AND deleted_at IS NULL", (fb_id,))
        _audit(cur, "feedback", fb_id, "soft_delete")
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok"}
