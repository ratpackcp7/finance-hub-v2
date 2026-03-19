"""Payee rules router — CRUD with soft deletes."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_read, db_transaction, require_nonempty, require_valid_category

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["rules"])


@router.get("/payee-rules")
def get_payee_rules():
    with db_read() as cur:
        cur.execute(
            "SELECT r.id, r.match_pattern, r.payee_name, r.category_id, c.name, r.priority "
            "FROM payee_rules r LEFT JOIN categories c ON r.category_id = c.id "
            "WHERE r.deleted_at IS NULL ORDER BY r.priority DESC, r.id")
        rows = cur.fetchall()
    return [{"id": r[0], "pattern": r[1], "payee_name": r[2], "category_id": r[3],
             "category": r[4], "priority": r[5]} for r in rows]


class PayeeRuleCreate(BaseModel):
    match_pattern: str
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    priority: int = 0


@router.post("/payee-rules", status_code=201)
def create_payee_rule(body: PayeeRuleCreate):
    with db_transaction() as cur:
        pattern = require_nonempty(body.match_pattern, "match_pattern").lower()
        if body.category_id is not None:
            require_valid_category(cur, body.category_id)
        cur.execute("SELECT id FROM payee_rules WHERE match_pattern = %s AND deleted_at IS NULL", (pattern,))
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE payee_rules SET category_id = COALESCE(%s, category_id), "
                "payee_name = COALESCE(%s, payee_name), priority = %s WHERE id = %s",
                (body.category_id, body.payee_name, body.priority, existing[0]))
            new_id = existing[0]
        else:
            cur.execute(
                "INSERT INTO payee_rules (match_pattern, payee_name, category_id, priority) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (pattern, body.payee_name, body.category_id, body.priority))
            new_id = cur.fetchone()[0]
        cur.execute(
            """UPDATE transactions
               SET category_id = %s,
                   payee = COALESCE(%s, payee),
                   category_source = 'rule',
                   updated_at = NOW()
               WHERE category_id IS NULL AND category_manual = FALSE
               AND (lower(description) LIKE %s OR lower(COALESCE(payee,'')) LIKE %s)""",
            (body.category_id, body.payee_name, f"%{pattern}%", f"%{pattern}%"))
        retro = cur.rowcount
        if retro > 0:
            _audit(cur, "payee_rule", new_id, "retroactive_apply", source="rule",
                   field_name="transactions_categorized", new_value=retro)
        logger.info("Rule %s (pattern=%s): retroactively categorized %d transactions", new_id, pattern, retro)
    return {"id": new_id, "retroactive": retro}


@router.delete("/payee-rules/{rule_id}")
def delete_payee_rule(rule_id: int):
    with db_transaction() as cur:
        cur.execute("SELECT match_pattern FROM payee_rules WHERE id = %s AND deleted_at IS NULL", (rule_id,))
        old = cur.fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Rule not found")
        cur.execute("UPDATE payee_rules SET deleted_at = NOW() WHERE id = %s", (rule_id,))
        _audit(cur, "payee_rule", rule_id, "soft_delete", field_name="pattern", old_value=old[0])
    return {"status": "ok"}


# ── Advanced Rules: Preview + Multi-condition ──

class AdvancedRuleCreate(BaseModel):
    match_pattern: str
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    priority: int = 0
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    set_transfer: Optional[bool] = None
    tag_id: Optional[int] = None
    description: Optional[str] = None


@router.post("/payee-rules/advanced", status_code=201)
def create_advanced_rule(body: AdvancedRuleCreate):
    with db_transaction() as cur:
        pattern = require_nonempty(body.match_pattern, "match_pattern").lower()
        if body.category_id is not None:
            require_valid_category(cur, body.category_id)
        cur.execute(
            "INSERT INTO payee_rules (match_pattern, payee_name, category_id, priority, "
            "amount_min, amount_max, set_transfer, tag_id, description) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (pattern, body.payee_name, body.category_id, body.priority,
             body.amount_min, body.amount_max, body.set_transfer,
             body.tag_id, body.description))
        new_id = cur.fetchone()[0]
        conds = ["category_id IS NULL", "category_manual = FALSE",
                 "(lower(description) LIKE %s OR lower(COALESCE(payee,'')) LIKE %s)"]
        params = [f"%{pattern}%", f"%{pattern}%"]
        if body.amount_min is not None:
            conds.append("ABS(amount) >= %s"); params.append(body.amount_min)
        if body.amount_max is not None:
            conds.append("ABS(amount) <= %s"); params.append(body.amount_max)
        ups, up = [], []
        if body.category_id is not None:
            ups += ["category_id = %s", "category_source = 'rule'"]; up.append(body.category_id)
        if body.payee_name:
            ups.append("payee = COALESCE(%s, payee)"); up.append(body.payee_name)
        if body.set_transfer is not None:
            ups.append("is_transfer = %s"); up.append(body.set_transfer)
        retro = 0
        if ups:
            ups.append("updated_at = NOW()")
            cur.execute(f"UPDATE transactions SET {', '.join(ups)} WHERE {' AND '.join(conds)}", up + params)
            retro = cur.rowcount
    return {"id": new_id, "retroactive": retro}


@router.get("/payee-rules/preview")
def preview_rules(pattern: str, amount_min: Optional[float] = None,
                  amount_max: Optional[float] = None, limit: int = 50):
    with db_read() as cur:
        p = pattern.lower().strip()
        conds = ["(lower(t.description) LIKE %s OR lower(COALESCE(t.payee,'')) LIKE %s)", "t.pending = FALSE"]
        params = [f"%{p}%", f"%{p}%"]
        if amount_min is not None:
            conds.append("ABS(t.amount) >= %s"); params.append(amount_min)
        if amount_max is not None:
            conds.append("ABS(t.amount) <= %s"); params.append(amount_max)
        w = " AND ".join(conds)
        cur.execute(
            f"SELECT t.id, t.posted, t.amount, t.description, t.payee, t.category_id, c.name, a.name "
            f"FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            f"JOIN accounts a ON t.account_id = a.id WHERE {w} ORDER BY t.posted DESC LIMIT %s", params + [limit])
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*) FROM transactions t LEFT JOIN categories c ON t.category_id = c.id WHERE {w}", params)
        total = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM transactions t LEFT JOIN categories c ON t.category_id = c.id WHERE {w} AND t.category_id IS NULL AND t.category_manual = FALSE", params)
        uncat = cur.fetchone()[0]
    return {"pattern": pattern, "total_matches": total, "uncategorized_matches": uncat,
            "preview": [{"id": r[0], "posted": r[1].isoformat() if r[1] else None,
                         "amount": float(r[2]), "description": r[3], "payee": r[4],
                         "category_id": r[5], "category": r[6], "account_name": r[7]} for r in rows]}


@router.get("/payee-rules/full")
def get_full_rules():
    with db_read() as cur:
        cur.execute(
            "SELECT r.id, r.match_pattern, r.payee_name, r.category_id, c.name, "
            "r.priority, r.amount_min, r.amount_max, r.set_transfer, r.tag_id, "
            "t.name, r.description "
            "FROM payee_rules r LEFT JOIN categories c ON r.category_id = c.id "
            "LEFT JOIN tags t ON r.tag_id = t.id "
            "WHERE r.deleted_at IS NULL ORDER BY r.priority DESC, r.id")
        rows = cur.fetchall()
    return [{"id": r[0], "pattern": r[1], "payee_name": r[2], "category_id": r[3],
             "category": r[4], "priority": r[5],
             "amount_min": float(r[6]) if r[6] else None, "amount_max": float(r[7]) if r[7] else None,
             "set_transfer": r[8], "tag_id": r[9], "tag": r[10], "description": r[11]} for r in rows]
