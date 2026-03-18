"""
Finance Hub v2 — Database pool + shared utilities
"""
import logging
import os
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.pool

logger = logging.getLogger(__name__)

ACCOUNT_TYPES = {
    "checking", "savings", "credit", "investment", "retirement",
    "529", "utma", "hsa", "brokerage", "loan", "mortgage", "other",
}

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
