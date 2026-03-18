"""Audit log router — read-only."""
from typing import Optional

from fastapi import APIRouter

from db import db_conn, db_put

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit-log")
def get_audit_log(entity_type: Optional[str] = None, entity_id: Optional[str] = None, limit: int = 100):
    conn = db_conn()
    try:
        cur = conn.cursor()
        f = []; p = []
        if entity_type:
            f.append("entity_type = %s"); p.append(entity_type)
        if entity_id:
            f.append("entity_id = %s"); p.append(entity_id)
        where = ("WHERE " + " AND ".join(f)) if f else ""
        cur.execute(
            f"SELECT id, entity_type, entity_id, action, field_name, old_value, new_value, source, created_at "
            f"FROM audit_log {where} ORDER BY created_at DESC LIMIT %s", p + [limit])
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "entity_type": r[1], "entity_id": r[2], "action": r[3],
             "field": r[4], "old": r[5], "new": r[6], "source": r[7],
             "at": r[8].isoformat() if r[8] else None} for r in rows]
