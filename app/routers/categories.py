"""Categories router — CRUD with soft deletes + validation."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_conn, db_put, require_nonempty, validate_color

router = APIRouter(prefix="/api", tags=["categories"])


@router.get("/categories")
def get_categories():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, color, group_name, is_income, sort_order "
            "FROM categories WHERE deleted_at IS NULL ORDER BY sort_order, name")
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "name": r[1], "color": r[2], "group": r[3],
             "is_income": r[4], "sort_order": r[5]} for r in rows]


class CategoryCreate(BaseModel):
    name: str
    color: str = "#64748b"
    group_name: Optional[str] = None
    is_income: bool = False


@router.post("/categories", status_code=201)
def create_category(body: CategoryCreate):
    name = require_nonempty(body.name, "name")
    validate_color(body.color)
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM categories WHERE lower(name) = lower(%s) AND deleted_at IS NULL", (name,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"Category '{name}' already exists")
        cur.execute(
            "INSERT INTO categories (name, color, group_name, is_income) VALUES (%s, %s, %s, %s) RETURNING id",
            (name, body.color, body.group_name, body.is_income))
        new_id = cur.fetchone()[0]
        conn.commit()
    finally:
        db_put(conn)
    return {"id": new_id, "name": name}


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM categories WHERE id = %s AND deleted_at IS NULL", (cat_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")
        if row[0] == "Uncategorized":
            raise HTTPException(status_code=400, detail="Cannot delete Uncategorized")
        cur.execute("UPDATE transactions SET category_id = NULL WHERE category_id = %s", (cat_id,))
        cur.execute("UPDATE payee_rules SET deleted_at = NOW() WHERE category_id = %s AND deleted_at IS NULL", (cat_id,))
        cur.execute("UPDATE budgets SET deleted_at = NOW() WHERE category_id = %s AND deleted_at IS NULL", (cat_id,))
        cur.execute("UPDATE categories SET deleted_at = NOW() WHERE id = %s", (cat_id,))
        _audit(cur, "category", cat_id, "soft_delete", field_name="name", old_value=row[0])
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok"}


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    group_name: Optional[str] = None
    is_income: Optional[bool] = None


@router.patch("/categories/{cat_id}")
def update_category(cat_id: int, body: CategoryUpdate):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name, color, group_name, is_income FROM categories WHERE id = %s AND deleted_at IS NULL",
                    (cat_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")
        old_name, old_color, old_group, old_income = row

        # Build dynamic update
        updates = []
        params = []

        if body.name is not None:
            name = require_nonempty(body.name, "name")
            if old_name == "Uncategorized":
                raise HTTPException(status_code=400, detail="Cannot rename Uncategorized")
            cur.execute("SELECT id FROM categories WHERE lower(name) = lower(%s) AND id != %s AND deleted_at IS NULL",
                        (name, cat_id))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail=f"Category '{name}' already exists")
            updates.append("name = %s")
            params.append(name)
            _audit(cur, "category", cat_id, "rename", field_name="name", old_value=old_name, new_value=name)

        if body.color is not None:
            validate_color(body.color)
            updates.append("color = %s")
            params.append(body.color)

        if body.group_name is not None:
            updates.append("group_name = %s")
            params.append(body.group_name if body.group_name else None)

        if body.is_income is not None:
            updates.append("is_income = %s")
            params.append(body.is_income)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        params.append(cat_id)
        sql = f"UPDATE categories SET {', '.join(updates)} WHERE id = %s"
        cur.execute(sql, params)
        conn.commit()
    finally:
        db_put(conn)

    return {"status": "ok", "id": cat_id}
