"""
Finance Hub v2 — Database pool + shared utilities
"""
import logging
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.pool
from fastapi import HTTPException

logger = logging.getLogger(__name__)

ACCOUNT_TYPES = {
    "checking", "savings", "credit", "investment", "retirement",
    "529", "utma", "hsa", "brokerage", "loan", "mortgage", "other",
}

MAX_TEXT_LEN = 2000  # general text field cap
MAX_NAME_LEN = 200   # names, patterns
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def read_secret(name: str) -> str:
    p = Path(f"/run/secrets/{name}")
    if p.exists():
        return p.read_text().strip()
    val = os.environ.get(name.upper())
    if val:
        return val
    raise RuntimeError(f"Secret '{name}' not found")


def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=10,
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", 5432)),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=read_secret("db_password"),
        )
    return _pool


def db_conn():
    return get_pool().getconn()


def db_put(conn):
    get_pool().putconn(conn)


def close_pool():
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


@contextmanager
def db_transaction():
    """Context manager for mutating DB operations.

    Yields a cursor. Commits on clean exit, rolls back on any exception.
    Connection always returns to the pool in a clean state.
    """
    conn = get_pool().getconn()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        get_pool().putconn(conn)


@contextmanager
def db_read():
    """Context manager for read-only DB operations.

    Yields a cursor. Rolls back on exit (no commit needed for reads)
    to ensure the connection returns clean.
    """
    conn = get_pool().getconn()
    try:
        cur = conn.cursor()
        yield cur
    finally:
        conn.rollback()
        get_pool().putconn(conn)



def _csv_safe(val):
    """Sanitize a value for CSV export to prevent formula injection."""
    if val is None:
        return ""
    s = str(val)
    if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + s
    return s


def _audit(cur, entity_type: str, entity_id, action: str, source: str = "user",
           field_name: str = None, old_value=None, new_value=None):
    """Append to audit_log. All values stored as text."""
    cur.execute(
        """INSERT INTO audit_log (entity_type, entity_id, action, field_name, old_value, new_value, source)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (entity_type, str(entity_id), action, field_name,
         str(old_value) if old_value is not None else None,
         str(new_value) if new_value is not None else None,
         source))


# ── Validation helpers ──

def require_valid_category(cur, category_id: int) -> str:
    """Verify category_id exists and isn't deleted. Returns category name. Raises 400 if invalid."""
    cur.execute("SELECT name FROM categories WHERE id = %s AND deleted_at IS NULL", (category_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail=f"Invalid category_id: {category_id}")
    return row[0]


def require_nonempty(value: str, field: str, max_len: int = MAX_NAME_LEN) -> str:
    """Strip and validate a non-empty string field. Returns stripped value."""
    v = (value or "").strip()
    if not v:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if len(v) > max_len:
        raise HTTPException(status_code=400, detail=f"{field} exceeds max length ({max_len})")
    return v


def validate_color(color: str) -> str:
    """Validate hex color format. Returns color."""
    if not COLOR_RE.match(color):
        raise HTTPException(status_code=400, detail=f"Invalid color format: {color} (expected #RRGGBB)")
    return color
