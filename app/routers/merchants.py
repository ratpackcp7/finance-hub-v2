"""Merchant management router — list, rename, merge payee names."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_conn, db_put

router = APIRouter(prefix="/api/merchants", tags=["merchants"])


@router.get("")
def list_merchants(search: Optional[str] = None, min_count: int = 1,
                   limit: int = 200, offset: int = 0):
    """List all unique payee/merchant names with transaction counts and totals."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        filters = ["t.pending = FALSE"]
        params = []

        if search:
            filters.append("(lower(COALESCE(t.payee, t.description)) LIKE %s)")
            params.append(f"%{search.lower()}%")

        where = " AND ".join(filters)

        cur.execute(
            f"""SELECT COALESCE(t.payee, t.description) as merchant,
                       COUNT(*) as txn_count,
                       SUM(ABS(t.amount)) as total_amount,
                       MIN(t.posted) as first_seen,
                       MAX(t.posted) as last_seen,
                       COUNT(DISTINCT t.account_id) as account_count
                FROM transactions t
                WHERE {where}
                AND COALESCE(t.payee, t.description) IS NOT NULL
                AND COALESCE(t.payee, t.description) != ''
                GROUP BY COALESCE(t.payee, t.description)
                HAVING COUNT(*) >= %s
                ORDER BY COUNT(*) DESC
                LIMIT %s OFFSET %s""",
            params + [min_count, limit, offset])
        rows = cur.fetchall()

        # Total count for pagination
        cur.execute(
            f"""SELECT COUNT(*) FROM (
                SELECT COALESCE(t.payee, t.description)
                FROM transactions t WHERE {where}
                AND COALESCE(t.payee, t.description) IS NOT NULL
                AND COALESCE(t.payee, t.description) != ''
                GROUP BY COALESCE(t.payee, t.description)
                HAVING COUNT(*) >= %s
            ) sub""", params + [min_count])
        total = cur.fetchone()[0]
    finally:
        db_put(conn)

    return {
        "total": total,
        "merchants": [
            {"name": r[0], "count": r[1],
             "total_amount": float(r[2]) if r[2] else 0,
             "first_seen": r[3].isoformat() if r[3] else None,
             "last_seen": r[4].isoformat() if r[4] else None,
             "accounts": r[5]}
            for r in rows
        ],
    }


class MerchantRename(BaseModel):
    old_name: str
    new_name: str


@router.post("/rename")
def rename_merchant(body: MerchantRename):
    """Rename all transactions with a specific payee to a new name."""
    old = (body.old_name or "").strip()
    new = (body.new_name or "").strip()
    if not old or not new:
        raise HTTPException(status_code=400, detail="old_name and new_name required")
    if old == new:
        return {"status": "no-op", "updated": 0}

    conn = db_conn()
    try:
        cur = conn.cursor()
        # Update payee field
        cur.execute(
            "UPDATE transactions SET payee = %s, updated_at = NOW() "
            "WHERE (payee = %s OR (payee IS NULL AND description = %s)) "
            "AND reconciled_at IS NULL",
            (new, old, old))
        updated = cur.rowcount

        _audit(cur, "merchant", old, "rename", source="user",
               field_name="payee", old_value=old, new_value=new)
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "updated": updated, "old_name": old, "new_name": new}


class MerchantMerge(BaseModel):
    source_names: list[str]
    target_name: str
    create_rule: bool = True


@router.post("/merge")
def merge_merchants(body: MerchantMerge):
    """Merge multiple payee names into one canonical name.
    Optionally creates a payee rule for each source name."""
    target = (body.target_name or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="target_name required")
    if not body.source_names:
        raise HTTPException(status_code=400, detail="source_names required")

    sources = [s.strip() for s in body.source_names if s.strip() and s.strip() != target]
    if not sources:
        return {"status": "no-op", "updated": 0, "rules_created": 0}

    conn = db_conn()
    try:
        cur = conn.cursor()
        total_updated = 0

        for old_name in sources:
            cur.execute(
                "UPDATE transactions SET payee = %s, updated_at = NOW() "
                "WHERE (payee = %s OR (payee IS NULL AND description = %s)) "
                "AND reconciled_at IS NULL",
                (target, old_name, old_name))
            total_updated += cur.rowcount

            _audit(cur, "merchant", old_name, "merge", source="user",
                   field_name="payee", old_value=old_name, new_value=target)

        # Optionally create payee rules
        rules_created = 0
        if body.create_rule:
            for old_name in sources:
                pattern = old_name.lower()[:60]
                cur.execute(
                    "SELECT id FROM payee_rules WHERE match_pattern = %s AND deleted_at IS NULL",
                    (pattern,))
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO payee_rules (match_pattern, payee_name, priority) "
                        "VALUES (%s, %s, 0)", (pattern, target))
                    rules_created += 1

        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "updated": total_updated, "rules_created": rules_created,
            "target": target, "sources": sources}


@router.get("/duplicates")
def find_duplicate_merchants(threshold: float = 0.8, min_count: int = 2, limit: int = 50):
    """Find merchants that look like duplicates based on name similarity.
    Uses simple prefix/substring matching — not fuzzy matching."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        # Get all merchants with sufficient count
        cur.execute(
            """SELECT COALESCE(t.payee, t.description) as merchant, COUNT(*) as cnt
               FROM transactions t
               WHERE t.pending = FALSE
               AND COALESCE(t.payee, t.description) IS NOT NULL
               AND COALESCE(t.payee, t.description) != ''
               GROUP BY COALESCE(t.payee, t.description)
               HAVING COUNT(*) >= %s
               ORDER BY 2 DESC""", (min_count,))
        merchants = [(r[0], r[1]) for r in cur.fetchall()]
    finally:
        db_put(conn)

    # Simple grouping: find merchants that share a common prefix (first 8 chars, lowercase)
    from collections import defaultdict
    groups = defaultdict(list)
    for name, count in merchants:
        key = name.lower().strip()[:8]
        if len(key) >= 3:
            groups[key].append({"name": name, "count": count})

    # Filter to groups with 2+ members
    suggestions = []
    for key, members in groups.items():
        if len(members) >= 2:
            members.sort(key=lambda m: -m["count"])
            suggestions.append({
                "prefix": key,
                "suggested_name": members[0]["name"],  # Most common variant
                "variants": members,
                "total_txns": sum(m["count"] for m in members),
            })

    suggestions.sort(key=lambda s: -s["total_txns"])
    return {"suggestions": suggestions[:limit], "total_groups": len(suggestions)}
