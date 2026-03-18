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
        # Check for duplicate name
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


class CategoryRename(BaseModel):
    name: str


@router.patch("/categories/{cat_id}")
def rename_category(cat_id: int, body: CategoryRename):
    name = require_nonempty(body.name, "name")
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM categories WHERE id = %s AND deleted_at IS NULL", (cat_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")
        if row[0] == "Uncategorized":
            raise HTTPException(status_code=400, detail="Cannot rename Uncategorized")
        # Check for duplicate name (excluding self)
        cur.execute("SELECT id FROM categories WHERE lower(name) = lower(%s) AND id != %s AND deleted_at IS NULL",
                    (name, cat_id))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"Category '{name}' already exists")
        cur.execute("UPDATE categories SET name = %s WHERE id = %s", (name, cat_id))
        _audit(cur, "category", cat_id, "rename", field_name="name", old_value=row[0], new_value=name)
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "name": name}
