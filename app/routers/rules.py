"""Payee rules router — CRUD with soft deletes."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_conn, db_put, require_nonempty, require_valid_category

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["rules"])


@router.get("/payee-rules")
def get_payee_rules():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT r.id, r.match_pattern, r.payee_name, r.category_id, c.name, r.priority "
            "FROM payee_rules r LEFT JOIN categories c ON r.category_id = c.id "
            "WHERE r.deleted_at IS NULL ORDER BY r.priority DESC, r.id")
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "pattern": r[1], "payee_name": r[2], "category_id": r[3],
             "category": r[4], "priority": r[5]} for r in rows]


class PayeeRuleCreate(BaseModel):
    match_pattern: str
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    priority: int = 0


@router.post("/payee-rules", status_code=201)
def create_payee_rule(body: PayeeRuleCreate):
    conn = db_conn()
    try:
        cur = conn.cursor()
        pattern = require_nonempty(body.match_pattern, "match_pattern").lower()
        if body.category_id is not None:
            require_valid_category(cur, body.category_id)
        cur.execute("SELECT id FROM payee_rules WHERE match_pattern = %s AND deleted_at IS NULL", (pattern,))
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE payee_rules SET category_id = COALESCE(%s, category_id), "
                "payee_name = COALESCE(%s, payee_name) WHERE id = %s",
                (body.category_id, body.payee_name, existing[0]))
            new_id = existing[0]
        else:
            cur.execute(
                "INSERT INTO payee_rules (match_pattern, payee_name, category_id, priority) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (pattern, body.payee_name, body.category_id, body.priority))
            new_id = cur.fetchone()[0]
        cur.execute(
            """UPDATE transactions SET category_id = %s, payee = COALESCE(%s, payee), updated_at = NOW()
               WHERE category_id IS NULL AND category_manual = FALSE
               AND (lower(description) LIKE %s OR lower(COALESCE(payee,'')) LIKE %s)""",
            (body.category_id, body.payee_name, f"%{pattern}%", f"%{pattern}%"))
        retro = cur.rowcount
        if retro > 0:
            _audit(cur, "payee_rule", new_id, "retroactive_apply", source="rule",
                   field_name="transactions_categorized", new_value=retro)
        conn.commit()
        logger.info("Rule %s (pattern=%s): retroactively categorized %d transactions", new_id, pattern, retro)
    finally:
        db_put(conn)
    return {"id": new_id, "retroactive": retro}


@router.delete("/payee-rules/{rule_id}")
def delete_payee_rule(rule_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT match_pattern FROM payee_rules WHERE id = %s AND deleted_at IS NULL", (rule_id,))
        old = cur.fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Rule not found")
        cur.execute("UPDATE payee_rules SET deleted_at = NOW() WHERE id = %s", (rule_id,))
        _audit(cur, "payee_rule", rule_id, "soft_delete", field_name="pattern", old_value=old[0])
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok"}
